import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";

const FEATURES: { title: string; description: string }[] = [
  {
    title: "Seven-agent pipeline",
    description:
      "Document analysis, requirement extraction, plan architecture, test generation, traceability, and quality review run as cooperating LangGraph agents.",
  },
  {
    title: "Full traceability",
    description:
      "Every test case links to the requirement it covers, and every requirement links back to the source paragraph it came from.",
  },
  {
    title: "Human-in-the-loop",
    description:
      "Interactive mode pauses at three checkpoints so engineers can accept, reprompt, or send free-text feedback before the pipeline continues.",
  },
  {
    title: "Defect detection engine",
    description:
      "38-entry defect taxonomy combining static checks, LLM critique, and traceability analysis, deduplicated into one auditable report.",
  },
  {
    title: "Provider-neutral LLMs",
    description:
      "Routes to OpenAI, Anthropic, or Gemini via a LiteLLM gateway, with no vendor lock-in for regulated industries.",
  },
  {
    title: "Standards-aware output",
    description:
      "Test plans follow the IEEE 829 / Inflectra layout, with defect findings referencing IEEE 830, ISO 29148, ISTQB, DO-178C, and IEC 61508.",
  },
];

export function HomePage() {
  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <img src="/sigmaxis-logo.png" alt="Sigmaxis" className="h-9 w-9 object-contain" />
            <span className="font-semibold">AI Test Plan Generator</span>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/signup">
              <Button size="sm">
                Create account
              </Button>
            </Link>
            <Link to="/login">
              <Button variant="outline" size="sm">
                Sign in
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-4 py-16 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          From engineering specs to traceable test plans
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          A multi-agent platform that turns specifications into ISO-compliant,
          fully-traceable test plans, built for QA and V&amp;V teams in
          aerospace, automotive, energy, and medical industries.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link to="/signup">
            <Button size="lg">Create account</Button>
          </Link>
          <Link to="/login">
            <Button variant="outline" size="lg">Sign in</Button>
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-20">
        <h2 className="text-center text-2xl font-semibold">What it does</h2>
        <p className="mx-auto mt-2 max-w-2xl text-center text-muted-foreground">
          Upload a spec (PDF, DOCX, or Markdown). The pipeline extracts every
          normative requirement, drafts a test plan, writes test cases, runs
          a quality review, and builds a coverage matrix, with you in
          control at every checkpoint.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <Card key={feature.title}>
              <CardHeader>
                <CardTitle>{feature.title}</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="text-sm text-muted-foreground">{feature.description}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      <footer className="border-t border-border py-6 text-center text-sm text-muted-foreground">
        <div className="flex items-center justify-center gap-2">
          <img src="/sigmaxis-logo.png" alt="Sigmaxis" className="h-5 w-5 object-contain" />
          <span>Built by Sigmaxis, for engineers who need traceability, not magic.</span>
        </div>
      </footer>
    </div>
  );
}
