import { Wordmark } from "@/components/Logo";

async function currentYear() {
  return new Date().getFullYear();
}

export async function Footer() {
  const year = await currentYear();
  return (
    <footer>
      <div className="mx-auto flex max-w-[1240px] flex-col gap-3 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <Wordmark />
        <p className="font-mono text-[11.5px] text-muted">
          Aster © {year}
        </p>
      </div>
    </footer>
  );
}
