import Link from "next/link";

import { isClerkConfigured } from "@/lib/auth";
import { LandingAuthButtons } from "./landing-auth-buttons";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
            A
          </div>
          <span className="text-lg font-semibold">ORION</span>
        </div>
        <LandingAuthButtons />
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-24 pt-16">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-4 text-sm font-medium uppercase tracking-wide text-accent">
            AI Executive Intelligence
          </p>
          <h1 className="mb-6 text-5xl font-bold tracking-tight text-foreground">
            Make better business decisions from your internal data
          </h1>
          <p className="mb-10 text-lg text-muted-foreground">
            Ask company questions, investigate business changes, and get conclusions
            backed by measured data and source evidence.
          </p>
          <LandingAuthButtons variant="hero" />
          {!isClerkConfigured && (
            <p className="mt-4 text-sm text-muted-foreground">
              Dev mode: add Clerk keys to <code className="text-xs">.env.local</code> to
              enable authentication.
            </p>
          )}
        </div>

        <div className="mt-24 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              title: "Executive summaries",
              description: "Auto-generated overviews from your uploaded documents.",
            },
            {
              title: "Natural language Q&A",
              description: "Ask questions instead of searching through files.",
            },
            {
              title: "Action items",
              description: "Extract tasks from meeting notes and tickets.",
            },
            {
              title: "Source citations",
              description: "Every answer links back to the original documents.",
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-border bg-white p-6"
            >
              <h3 className="mb-2 font-semibold">{feature.title}</h3>
              <p className="text-sm text-muted-foreground">{feature.description}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
