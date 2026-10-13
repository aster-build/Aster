"""Bounded supervised encoder adaptation using only revealed measurements."""
from pathlib import Path
import numpy as np
from .data import digest
from .heads import make_head


class AdaptedCheMeleon:
    def __init__(self, recipe, settings, checkpoint, expected_hash, seed):
        self.recipe, self.settings = recipe, settings
        self.checkpoint, self.expected_hash, self.seed = Path(checkpoint), expected_hash, seed

    def _graphs(self, structures):
        from chemprop.data import BatchMolGraph
        from rdkit import Chem
        return BatchMolGraph([self.featurizer(Chem.MolFromSmiles(s)) for s in structures])

    def _features(self, structures):
        import torch
        blocks = []
        self.encoder.eval()
        with torch.no_grad():
            for start in range(0, len(structures), self.settings['batch_size']):
                graph = self._graphs(structures[start:start + self.settings['batch_size']])
                blocks.append(self.aggregation(self.encoder(graph), graph.batch).cpu().numpy())
        x = np.concatenate(blocks)
        if not np.isfinite(x).all():
            raise ValueError('Nonfinite adapted embeddings')
        return x

    def fit(self, structures, y):
        import torch
        from chemprop import featurizers, nn
        if digest(self.checkpoint) != self.expected_hash:
            raise ValueError('Checkpoint checksum mismatch')
        torch.set_num_threads(self.settings['threads'])
        torch.manual_seed(self.seed)
        torch.use_deterministic_algorithms(True)
        weights = torch.load(self.checkpoint, weights_only=True, map_location='cpu')
        self.encoder = nn.BondMessagePassing(**weights['hyper_parameters'])
        self.encoder.load_state_dict(weights['state_dict'])
        self.aggregation = nn.MeanAggregation()
        self.featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
        x = self._features(structures)
        initial_head = make_head(self.recipe).fit(x, y)
        coef, bias = initial_head.linear_coefficients()
        mean, scale = float(np.mean(y)), max(float(np.std(y)), 1e-6)
        auxiliary = torch.nn.Linear(x.shape[1], 1)
        with torch.no_grad():
            auxiliary.weight.copy_(torch.tensor(coef / scale, dtype=torch.float32)[None])
            auxiliary.bias.fill_((bias - mean) / scale)
        normalized = torch.tensor((np.asarray(y) - mean) / scale, dtype=torch.float32)
        optimizer = torch.optim.AdamW([
            {'params': self.encoder.parameters(), 'lr': self.settings['encoder_lr']},
            {'params': auxiliary.parameters(), 'lr': self.settings['head_lr']}
        ], weight_decay=self.settings['weight_decay'])
        rng = np.random.default_rng(self.seed)
        losses = []
        self.encoder.train()
        for epoch in range(self.settings['epochs']):
            order = rng.permutation(len(structures))
            total = 0.
            for start in range(0, len(order), self.settings['batch_size']):
                indices = order[start:start + self.settings['batch_size']]
                graph = self._graphs(structures[indices])
                optimizer.zero_grad(set_to_none=True)
                p = auxiliary(self.aggregation(self.encoder(graph), graph.batch)).squeeze(-1)
                loss = torch.nn.functional.mse_loss(p, normalized[indices])
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite training loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(list(self.encoder.parameters()) + list(auxiliary.parameters()),
                                               self.settings['gradient_norm_max'], error_if_nonfinite=True)
                optimizer.step()
                total += float(loss.detach()) * len(indices)
            losses.append(total / len(structures))
        delta = sum(float(torch.sum((v.detach() - weights['state_dict'][k]) ** 2))
                    for k, v in self.encoder.state_dict().items()) ** .5
        self.head = make_head(self.recipe).fit(self._features(structures), y)
        self.diagnostics_ = {'n_observed': len(y), 'epochs': self.settings['epochs'],
                             'normalized_training_mse': losses, 'encoder_weight_l2_change': delta,
                             'target_mean': mean, 'target_scale': scale,
                             'features_retained': int(self.head.mask_.sum())}
        return self

    def predict(self, structures):
        return self.head.predict(self._features(structures))
