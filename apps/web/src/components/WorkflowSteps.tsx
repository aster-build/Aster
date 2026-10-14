import { ChevronRight } from '@/components/icons';

/** Progress through the live campaign workflow. */
export function WorkflowSteps({ current }: { current: number }) {
  return (
    <ol aria-label="Workflow" className="flex w-full items-center gap-1 text-[12px] sm:w-auto sm:gap-2">
      {['Predict', 'Prioritize', 'Test', 'Learn'].map((name, index) => (
        <li key={name} aria-current={index === current ? 'step' : undefined} className="flex flex-1 items-center sm:flex-none">
          <span className={`flex w-full items-center justify-center gap-1.5 rounded-[5px] px-2 py-1.5 ${index === current ? 'bg-accent-soft font-medium text-accent-strong' : index < current ? 'text-ink-2' : 'text-muted'}`}>
            <span className="hidden font-mono text-[10px] opacity-70 min-[400px]:inline">0{index + 1}</span>
            {name}
          </span>
          {index < 3 && <span aria-hidden="true" className="hidden pl-2 text-faint sm:block"><ChevronRight size={12} weight={2.2} /></span>}
        </li>
      ))}
    </ol>
  );
}
