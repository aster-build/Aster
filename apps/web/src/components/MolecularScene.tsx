'use client';
import { useEffect, useRef, useState } from 'react';
import { PluginContext } from 'molstar/lib/mol-plugin/context';
import { DefaultPluginSpec } from 'molstar/lib/mol-plugin/spec';
import { MolScriptBuilder as MS } from 'molstar/lib/mol-script/language/builder';
import { Script } from 'molstar/lib/mol-script/script';
import { Structure, StructureElement, StructureSelection, StructureProperties } from 'molstar/lib/mol-model/structure';
import { OrderedSet } from 'molstar/lib/mol-data/int';
import { Color } from 'molstar/lib/mol-util/color';
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra';
import type { Contact, StructureEvidence } from '@/lib/replay';

type Props = { candidateSdf?:string; evidence:StructureEvidence; view:'protein'|'pocket'|'ligand'; contact:Contact|null; onResidue:(sequence:number)=>void };
export default function MolecularScene({evidence,view,contact,onResidue,candidateSdf}:Props) {
  const host=useRef<HTMLDivElement>(null);
  const plugin=useRef<PluginContext|null>(null);
  const structure=useRef<Structure|null>(null);
  const onPick=useRef(onResidue); onPick.current=onResidue;
  const [ready,setReady]=useState(false); const [error,setError]=useState('');
  useEffect(()=>{
    let cancelled=false; let observer:ResizeObserver|undefined;
    const p=new PluginContext({...DefaultPluginSpec(),canvas3d:{renderer:{backgroundColor:Color(0xf3f3ef)},camera:{mode:'perspective'}}});
    plugin.current=p;
    async function load() {
      try {
        await p.init(); if(cancelled)return;
        const mounted=await p.mountAsync(host.current!); if(!mounted)throw Error('WebGL is unavailable in this browser.');
        const data=await p.builders.data.download({url:'/structures/8y2g/complex.cif',isBinary:false});
        const trajectory=await p.builders.structure.parseTrajectory(data,'mmcif');
        const model=await p.builders.structure.createModel(trajectory);
        const s=await p.builders.structure.createStructure(model,{name:'model',params:{}});
        structure.current=s.obj!.data;
        const protein=await p.builders.structure.tryCreateComponentStatic(s,'polymer');
        if(protein)await p.builders.structure.representation.addRepresentation(protein,{type:'cartoon',color:'uniform',colorParams:{value:Color(0x99aaa8)},typeParams:{alpha:0.62}});
        const ligandExpr=MS.struct.generator.atomGroups({'residue-test':MS.core.rel.eq([MS.struct.atomProperty.macromolecular.label_comp_id(),evidence.ligand_component])});
        const ligand=await p.builders.structure.tryCreateComponentFromExpression(s,ligandExpr,'reference-ligand');
        if(ligand)await p.builders.structure.representation.addRepresentation(ligand,{type:'ball-and-stick',color:'element-symbol',colorParams:{carbonColor:{name:'uniform',params:{value:Color(0x7251d2)}}},typeParams:{sizeFactor:0.35}});
        const pocketExpr=MS.struct.generator.atomGroups({'chain-test':MS.core.rel.eq([MS.struct.atomProperty.macromolecular.auth_asym_id(),'A']),'residue-test':MS.core.set.has([MS.set(...evidence.contacts.map(c=>c.sequence)),MS.struct.atomProperty.macromolecular.auth_seq_id()])});
        const pocket=await p.builders.structure.tryCreateComponentFromExpression(s,pocketExpr,'pocket');
        if(pocket)await p.builders.structure.representation.addRepresentation(pocket,{type:'ball-and-stick',color:'element-symbol',colorParams:{carbonColor:{name:'uniform',params:{value:Color(0x999d9a)}}},typeParams:{sizeFactor:0.18}});
        observer=new ResizeObserver(()=>p.handleResize()); observer.observe(host.current!);
        p.behaviors.interaction.click.subscribe(event=>{
          if(!StructureElement.Loci.is(event.current.loci)||!event.current.loci.elements.length)return;
          const loci=event.current.loci;const first=loci.elements[0];
          const loc=StructureElement.Location.create(loci.structure,first.unit,first.unit.elements[OrderedSet.getAt(first.indices,0)]);
          if(StructureProperties.chain.auth_asym_id(loc)==='A')onPick.current(StructureProperties.residue.auth_seq_id(loc));
        });
        if(!cancelled)setReady(true);
      }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'Unable to load molecular structure.');}
    }
    load();
    return ()=>{cancelled=true;observer?.disconnect();plugin.current=null;structure.current=null;p.dispose();};
  },[evidence]);
  useEffect(()=>{
    const p=plugin.current;if(!ready||!p||!candidateSdf)return;
    let cancelled=false;let dataRef:string|undefined;
    async function overlay(){
      try{
        const data=await p!.builders.data.rawData({data:candidateSdf!,label:'Predicted candidate pose'});dataRef=data.ref;
        if(cancelled){await p!.state.data.build().delete(data.ref).commit();return;}
        const trajectory=await p!.builders.structure.parseTrajectory(data,'sdf');
        const model=await p!.builders.structure.createModel(trajectory);
        const s=await p!.builders.structure.createStructure(model);
        const component=await p!.builders.structure.tryCreateComponentStatic(s,'all');
        if(component&&!cancelled)await p!.builders.structure.representation.addRepresentation(component,{type:'ball-and-stick',color:'element-symbol',colorParams:{carbonColor:{name:'uniform',params:{value:Color(0x168765)}}},typeParams:{sizeFactor:0.3}});
        if(cancelled){await p!.state.data.build().delete(data.ref).commit();return;}
        p!.managers.camera.focusSphere({center:Vec3.create(...evidence.ligand_center as [number,number,number]),radius:13},{durationMs:0});
      }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'Candidate rendering failed');}
    }
    overlay();return()=>{cancelled=true;if(dataRef&&plugin.current===p)p.state.data.build().delete(dataRef).commit();};
  },[candidateSdf,ready,evidence]);
  useEffect(()=>{
    const p=plugin.current;const s=structure.current;if(!ready||!p||!s)return;
    const duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:650;
    let cancelled=false; let measurementRef:string|undefined;
    if(contact){
      const expression=MS.struct.generator.atomGroups({'chain-test':MS.core.rel.eq([MS.struct.atomProperty.macromolecular.auth_asym_id(),contact.chain]),'residue-test':MS.core.rel.eq([MS.struct.atomProperty.macromolecular.auth_seq_id(),contact.sequence])});
      const loci=StructureSelection.toLociWithSourceUnits(Script.getStructureSelection(expression,s));
      p.managers.interactivity.lociSelects.selectOnly({loci},false);
      const atomLoci=(chain:string,seq:number,atom:string)=>StructureSelection.toLociWithSourceUnits(Script.getStructureSelection(MS.struct.generator.atomGroups({"chain-test":MS.core.rel.eq([MS.struct.atomProperty.macromolecular.auth_asym_id(),chain]),"residue-test":MS.core.rel.eq([MS.struct.atomProperty.macromolecular.auth_seq_id(),seq]),"atom-test":MS.core.rel.eq([MS.struct.atomProperty.macromolecular.label_atom_id(),atom])}),s));
      p.managers.structure.measurement.addDistance(atomLoci(contact.chain,contact.sequence,contact.protein_atom),atomLoci(evidence.ligand_auth_chain,evidence.ligand_auth_sequence,contact.ligand_atom),{customText:`${contact.distance.toFixed(2)} Å · proximity`}).then(result=>{if(!result)return;if(cancelled){p.state.data.build().delete(result.selection.ref).commit();}else measurementRef=result.selection.ref;}).catch(()=>{ /* The verified distance is still available in the table. */ });
      const center=Vec3.create(...contact.protein_xyz as [number,number,number]);
      p.managers.camera.focusSphere({center,radius:7},{durationMs:duration});
    }else{
      p.managers.interactivity.lociSelects.deselectAll();
      if(view==='protein')p.managers.camera.reset(undefined,duration);
      else p.managers.camera.focusSphere({center:Vec3.create(...evidence.ligand_center as [number,number,number]),radius:view==='pocket'?13:6},{durationMs:duration});
    }
    return()=>{cancelled=true;if(measurementRef&&plugin.current===p)p.state.data.build().delete(measurementRef).commit();};
  },[view,contact,ready,evidence]);
  return <><div ref={host} className="molecular-canvas" aria-label="Interactive 3D experimental reference protein and bound ligand" data-ready={ready} data-candidate={Boolean(candidateSdf)}/>{ready&&error&&<div className="scene-status" role="alert">{error}</div>}{!ready&&<div className="scene-status" role="status">{error||'Loading experimental structure…'}{error&&<p>The residue-distance table and campaign replay remain available.</p>}</div>}</>;
}
