"use client";

import { ArrowDownToLine, DocText, Flask, Hexagon } from "@/components/icons";
import { Lede, Reveal, SectionTitle, StatusLabel, useInView } from "@/components/ui";
import { assayRows, assayRowsToCsv } from "@/lib/data";

const GROUPS = [
  { title: "Compound inputs", items: ["SMILES", "SDF", "Compound IDs"], Icon: Hexagon },
  {
    title: "Experimental context",
    items: ["Assay results", "Units", "Target identifiers", "Experimental conditions"],
    Icon: Flask,
  },
  { title: "Research outputs", items: ["Ranked CSV", "Candidate report", "Experiment history"], Icon: DocText },
];

function downloadCsv() {
  const blob = new Blob([assayRowsToCsv(assayRows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "aster-example-assay-data.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function DataWorkflow() {
  return (
    <section id="data" aria-labelledby="data-title" className="scroll-mt-20">
      <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-10 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-12 lg:gap-10 lg:py-24">
        <Reveal className="min-w-0 lg:col-span-5">
          <SectionTitle id="data-title">Bring your data. Keep the context.</SectionTitle>
          <Lede className="mt-6 max-w-[30rem]">
            A research workflow should preserve the measurements, assay conditions, and molecular identities
            behind each decision.
          </Lede>
          <p className="mt-5 max-w-[30rem] text-[15px] leading-relaxed text-muted">
            These formats describe the workflow we are designing toward. They are not live imports
            or third-party integrations.
          </p>
          <div className="mt-6">
            <StatusLabel tone="violet">Planned workflow</StatusLabel>
          </div>
        </Reveal>

        <div className="min-w-0 lg:col-span-7">
          <Chips />
        </div>


        <Reveal delay={100} className="min-w-0 lg:col-span-12 lg:mt-4">
        <figure className="overflow-hidden rounded-[12px] border border-line bg-stage">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
            <figcaption className="text-[13px] text-ink">
              <span className="font-medium">assay_results.csv</span>{" "}
              <span className="text-muted">· synthetic example rows</span>
            </figcaption>
            <button
              type="button"
              onClick={downloadCsv}
              className="inline-flex h-8 items-center gap-1.5 rounded-[6px] border border-line-strong bg-paper px-3 text-[12.5px] font-medium text-ink hover:bg-stage"
            >
              <ArrowDownToLine size={14} weight={2} />
              Download example CSV
            </button>
          </div>
          <div className="overflow-x-auto bg-paper" tabIndex={0} role="region" aria-label="Example assay table, scrollable">
            <table className="w-full min-w-[640px] border-collapse whitespace-nowrap text-left font-mono text-[12px]">
              <thead>
                <tr className="border-b border-line text-[11px] text-muted">
                  <th scope="col" className="px-4 py-2 font-normal">compound_id</th>
                  <th scope="col" className="px-3 py-2 font-normal">endpoint</th>
                  <th scope="col" className="px-3 py-2 text-right font-normal">value</th>
                  <th scope="col" className="px-3 py-2 font-normal">unit</th>
                  <th scope="col" className="px-3 py-2 font-normal">target</th>
                  <th scope="col" className="px-3 py-2 font-normal">conditions</th>
                  <th scope="col" className="px-4 py-2 font-normal">experiment</th>
                </tr>
              </thead>
              <tbody>
                {assayRows.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-b-0">
                    <td className="px-4 py-2.5 font-medium text-ink">{r.id}</td>
                    <td className="px-3 py-2.5 text-ink-2">{r.endpoint}</td>
                    <td className="px-3 py-2.5 text-right text-ink tabular-nums">{r.value.toLocaleString("en-US")}</td>
                    <td className="px-3 py-2.5 text-ink-2">{r.unit}</td>
                    <td className="px-3 py-2.5 text-ink-2">{r.target}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-muted">{r.conditions}</td>
                    <td className="px-4 py-2.5 text-accent-strong">{r.experiment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
            Each value keeps its unit, target, conditions and experiment reference. These rows are the
            assayed analogs referenced in the shortlist above.
          </p>
        </figure>
        </Reveal>
      </div>
    </section>
  );
}

function Chips() {
  const [ref, inView] = useInView<HTMLDivElement>();
  let k = 0;
  return (
    <div ref={ref} className="space-y-7">
      {GROUPS.map((g) => (
        <div key={g.title}>
          <h3 className="text-[14px] text-muted">{g.title}</h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {g.items.map((item) => {
              const delay = 80 + k++ * 55;
              return (
                <li
                  key={item}
                  style={{ transitionDelay: `${delay}ms` }}
                  className={`inline-flex h-10 items-center gap-2 rounded-[8px] border border-line-strong bg-paper px-3.5 text-[14.5px] text-ink motion-safe:transition-[opacity,transform] motion-safe:duration-700 motion-safe:ease-[cubic-bezier(0.16,1,0.3,1)] ${
                    inView ? "" : "motion-safe:translate-y-2 motion-safe:opacity-0"
                  }`}
                >
                  <g.Icon size={16} weight={1.8} className="text-accent" />
                  {item}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
