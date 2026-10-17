# Intara as a Portfolio Project — Keep It, Package It, Prove It

Prepared 17 October 2026 for a 4th-year BTech (AI and Data Science) student applying for internships.

## Verdict

Keep it. Don't delete it, and don't make it your only project. The fact that it was vibe-coded is not the problem. The problems would be not being able to explain it, or overselling it.

## Why it is worth keeping

Interviewers for AI-engineer and full-stack internships are rarely impressed by "I built an app builder". They are impressed by evidence that you know how to make LLM systems reliable. You have that, and most student projects don't:

- Schema-validated LLM output with repair loops and tracked parse failures.
- An eval harness with a measured pass rate, plus honest failure analysis.
- A durable run engine that resumes after a crash.
- A hand-written formula parser with Python and TypeScript conformance tests.
- Roughly 400 automated tests and fail-closed gates.

Your best interview material is the failures you found: silent template fallbacks hiding a 0/21 parse rate, the eval overfitting, and the "hollow resume" bug.

## The vibe-coding risk, handled honestly

In 2026 employers expect AI-assisted work. The red flags are:

- You can't explain your own code.
- The demo is broken.
- Secrets are leaked in git history.
- You claim "production-grade" or "startup".

Say it plainly in the README: *built with AI coding agents; I specified the architecture, gates and evals, and verified the results.* Only claim what is true. If anyone asks "did you write this?", the honest answer is "I directed it, and here is what I can change live."

### Ownership test (pass it without AI help before you apply)

1. Why spec-first instead of generating code?
2. Walk through one wish from the prompt to the running preview.
3. How does your eval work, and what is wrong with the 17/20 number?
4. Explain the formula parser and the patch/invert logic.
5. What would you change with a paid API key, and with none?

Read the five or six core files once, end to end. If you can't answer these, either learn them or cut the project down to the parts you can defend.

## Package it in about 10 days

You are applying now, so cap this at 1–2 weeks of effort:

1. **Check git history for secrets.** Rotate any key that ever appeared there.
2. **Live demo link.** The runtime runs in the browser with no backend, so host a gallery of the 10 gold apps on a free static host. Recruiters will click a link; they won't clone a repo.
3. **Short README.** A diagram, a one-line pitch, a 2-minute demo video, and a Limitations section.
4. **One-page results write-up.** Use real numbers: 17/20 on the tuned set, 3/5 on held-out domains, and what you learned from both.
5. **Move AGENT.md and the session ledger** to a `docs/process` folder, linked only from the bottom of the README. Nobody will read hundreds of lines in a screen.
6. **Add GitHub Actions** to run the tests.

### Two free extras that strengthen the AI and data-science angle

- **Telemetry analysis.** A notebook analysing your `llm_calls` data: parse success by provider, latency, and failure causes.
- **Local-model experiment.** Compare a local model with constrained decoding against the free APIs on a blind set, and write up the result.

## Resume bullets

Keep them short and verify every number:

- Built Intara, a prompt-to-app generator where LLMs emit validated JSON specs run by a React/TypeScript runtime; developed with AI coding agents under my architecture and evals.
- Added schema, lint and generated-test gates and a 20-prompt eval (17/20 pass after tuning, 3/5 on held-out domains); about 200 Python and 200 Node tests.
- Implemented a resumable run engine with retries across free-tier LLM providers and per-call telemetry.

Only mention FitMantra usage if some of it is genuinely used there.

## Keep it in proportion

A project helps you in interviews, but it won't get you the internship alone. Your strongest languages are C, Java and C++, and online assessments test those. A realistic mix is:

- **One flagship.** This project, packaged as above.
- **One or two small projects** you can write and explain without AI, in a language you are fluent in. Reimplementing the formula parser in Java or C++ is a good example.
- **Daily DSA and SQL practice,** plus steady applications and referrals.

If you can't spare the 10 days, extract the two best parts into small repos: the formula parser with its conformance suite, and the eval harness. They are easier to review than the whole project.

## Next step

Decide which to do first: a draft README with a 2-minute demo script, or written answers to the five ownership-test questions.
