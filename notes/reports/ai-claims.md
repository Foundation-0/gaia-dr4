> The full report of the research agent that scouted checking what AI is claimed to have discovered for Foundation0 on 19 October 2026, kept as it was written. It is model output: a fact in it was checked against its source only where [fact-check.md](fact-check.md) says so. Paths starting with `scratch/` were the scouting session's temporary folder; see [README.md](README.md) for where those files are now.

**Scouting report: checking AI-claimed discoveries (19 Oct 2026)**

I read deep-fields/README.md, ledger.json (343 entries; 27 at "formally-verified", 21 "claimed", 31 contested) and the machine-mathematics page. Two new things f0 should know about:
- **whataifound.org** is a parallel registry of AI contributions: 179 entries, 118 of them "never independently checked". It catalogues and grades entries but says its text searches are "not a build and not a statement audit" (https://whataifound.org/).
- **Palomar** is a Lean registry incubated by the Lean FRO and ICARM, with Tao, Avigad and Morrison among its maintainers. It runs Comparator and has a language model judge statement fidelity. It has no human review step and only registers what authors submit (https://palomar-registry.org/about).

So cataloguing is crowded. Doing the checks yourself (builds, statement audits, re-runs) is not.

---

### 1. `formal-claims-audit` (best fit: Ryan Shea, with Ahraz)
**Question:** When an AI lab says a result is "Lean-verified", does its Lean theorem state what the paper claims?

**Why now**
- OpenAI says about 42% of top-line results in openai/math (released 6 Oct) are formalised. Independent recounts put it at 24% (173/719 manuscripts) or 36% (135/372 families), and "top-line" is never defined ([dev.to, 14 Oct](https://dev.to/getpack/maths-openai-posted-722-ai-proofs-42-machine-checked-3lbb)). f0's own Ledger repeats the 42%.
- For the 23 Erdős results in that release, Thomas Bloom says he "hasn't checked that the Lean formalisations compile or that the formal statements capture the original problems". The Lean file for Problem 3 proves only a weaker bound ([OfficeChai, 9 Oct](https://officechai.com/ai/openai-has-also-included-proofs-for-23-erdos-problems-in-its-latest-math-proof-drop/)).
- Bastounis, Circelli and Hansen argue the Navier–Stokes Lean code does not match the written proof ([arXiv:2610.08144](https://arxiv.org/abs/2610.08144)).
- The IAS-hosted advisory group says assessing the release is "up to the mathematical community" ([TechCrunch, 8 Oct](https://techcrunch.com/2026/10/08/openais-math-solutions-arent-meeting-the-fields-standards-yet/)).

**Who else is checking**
- Big O Speedrun runs Comparator against fixed statements, but only for 20 problems, and does not compare those statements with the papers ([about](https://bigospeedrun.com/about)).
- Palomar only registers what authors submit, and fidelity is judged by a language model.
- Sienicki & Sienicki audited the review record of OpenAI's ten August results, not the Lean statements ([arXiv:2608.14673](https://arxiv.org/abs/2608.14673)).
- One fork, grwtsk/openai-math, opened audit tickets in a single burst on 9 Oct ([issue](https://github.com/grwtsk/openai-math/issues/11)).
- Nobody is auditing claims across labs.

**How a result is checked:** a "blind restatement".
- Write each challenge statement independently of the lab's version: from the paper, or from DeepMind's formal-conjectures.
- Run `lake comparator` (Lean ≥4.35) and the nanoda second kernel ([Comparator](https://raw.githubusercontent.com/leanprover/comparator/master/README.md)).
- Print the axioms each proof uses.
- Anyone can re-run all of it.

**First step (about a day):** build the 19 Lean-formalised Erdős results from OpenAI's release at a pinned commit. Run Comparator against the formal-conjectures statement for each problem and publish a pass / weaker / mismatch table. Then do the same for the roughly 20 AI entries at "formally-verified" in the Ledger.

**Data and tools:** openai/math, anthropics/formal-math, formal-conjectures, Comparator, nanoda.

**Risks**
- Judging fidelity for deep results (Hodge, UGC) needs specialists.
- The independent statements can be wrong themselves: Erdős #124's formal statement had a typo (Ledger).
- Frame findings as "the formal statement differs", not "the proof is wrong".

**What would kill it:** Palomar or the Lean FRO starts auditing lab claims without waiting for submissions.

---

### 2. `ai-scientist-reruns` (fits rohanarun's Auto-research-agent)
**Question:** When automated scientists claim discoveries from public data, does an independent re-run get the same result?

**Why now**
- Three of the seven discoveries claimed by Kosmos (Edison) rest on public data ([arXiv:2511.02824](https://arxiv.org/html/2511.02824v2)):
  - log-normal connectivity across eight public connectomes;
  - SOD2 and myocardial fibrosis, by Mendelian randomisation on public pQTL and T1 GWAS data;
  - SSR1 and a type 2 diabetes variant, using DIAGRAM, GTEx and GEO data.
- Robin and Google's co-scientist are now in Nature (Ledger).
- A June 2026 survey of AI-scientist systems found 83% release code but only 38% release seeds or traces. It counted no external replications ([arXiv:2608.05179](https://arxiv.org/abs/2608.05179)).

**Who else is checking**
- I found no independent reanalysis of Kosmos, co-scientist, Robin or Biomni results. I searched for "reanalysis", "replicate" and "critique" with each name.
- There is a community re-implementation of Kosmos, but its developer says the paper's results have not been reproduced ([ai-deck](https://ai-deck.app/blog/kosmos/)).
- Beel et al. evaluated Sakana's v1 system: 42% of experiments failed on coding errors ([arXiv:2502.14297](https://arxiv.org/pdf/2502.14297)).
- Faraday replicates human-written papers, not AI claims ([arXiv:2608.13331](https://arxiv.org/html/2608.13331)).

**How a result is checked:** re-run the analysis from the public data and compare the reported effect sizes and p-values, within stated tolerances.

**First step (about a day):** re-run Kosmos discovery 4 (SOD2) from the public summary statistics with TwoSampleMR and coloc, and pre-register the comparison.

**Data and tools:** GWAS Catalog, GTEx, DIAGRAM, GEO, R/Bioconductor. The Kosmos reports are hosted on Edison's platform (Supplementary Table 1 of the paper).

**Risks**
- Four of the seven discoveries use collaborator data.
- A Mendelian randomisation analysis involves analyst choices, so a different number is not a refutation.
- There is reputational exposure with Edison, Google and FutureHouse.

**What would kill it:** the reports or trajectories turn out not to be public.

---

### 3. `crypto-reruns` (fits Ryan's autofoundry; Ahraz's AES S-box and GF(2^m) work)
**Question:** Do the AI-found cryptanalysis attacks actually recover keys when someone else runs them?

**Why now**
- On 28 Jul Anthropic claimed several attacks ([post](https://www.anthropic.com/research/discovering-cryptographic-weaknesses)):
  - HAWK-256 cut from 2^64 to 2^38;
  - a practical attack on 13-round LEA;
  - 6-round Serpent;
  - a faster attack on 7-round AES.
- Its released code recovers a HAWK-256 key in about 3 h 42 min on a 96-core server ([HAWK README](https://github.com/anthropics/cryptography-research-demo/blob/main/HAWK/README.md)).
- The LEA demo recovered 47 of 50 random keys, typically in about 5 minutes ([LEA README](https://github.com/anthropics/cryptography-research-demo/blob/main/LEA/README.md)).
- There are other AI-assisted claims too: a GPT-5.6 attack on HAWK and Saarinen's McEliece TII-252 break ([PostQuantum](https://postquantum.com/security-pqc/ai-cryptanalysis-hawk-aes/)).

**Who else is checking**
- Daniel Apon checked the HAWK reduction on paper, and the HAWK team "is verifying both" attacks.
- No end-to-end re-run is reported for any of these (same PostQuantum source).

**How a result is checked:** a recovered key produces a signature that verifies under the NIST reference code. For LEA, the recovered key decrypts a held-out block.

**First step (about a day):**
- Rent one AVX512-VNNI server.
- Generate three fresh HAWK-256 key pairs with the reference keygen. Do not use the shipped test keys.
- Run the attack on each, then run LEA on 200 random keys.

**Risks**
- Re-running the authors' own code is only partly independent. The real test is a reimplementation from the paper.
- Moderate significance: HAWK-512 and HAWK-1024 are unaffected.

**What would kill it:** the HAWK team or NIST publishes their own re-runs first.

---

### 4. `validated-planets` (fits eumemic; extends deep-fields #2)
**Question:** How many exoplanets "validated" by machine learning alone survive Gaia DR4?

**Why now**
- DR4, with epoch astrometry, comes out on 2 Dec 2026 ([ESA](https://www.cosmos.esa.int/web/gaia/news)).
- About 538 planets were validated by ML pipelines:
  - ExoMiner, 301 ([arXiv:2111.10009](https://arxiv.org/pdf/2111.10009));
  - ExoMiner's multiplicity boost, 69 ([arXiv:2305.02470](https://arxiv.org/abs/2305.02470));
  - Armstrong et al., 50 ([MNRAS](https://academic.oup.com/mnras/article/504/4/5327/5894933));
  - RAVEN, 118 (Ledger).
- There is precedent: Gaia DR3's non-single-star solutions refuted the validated planet K2-256 b ([arXiv:2310.12380](https://arxiv.org/abs/2310.12380)), and K2-399 b was demoted ([A&A 2024](https://www.aanda.org/articles/aa/full_html/2024/09/aa51398-24/aa51398-24.html)).

**Who else is checking:** I found no systematic re-audit of ML-validated planets, only case studies. The Gaia team (DPAC) will probably cross-match known planets on release (unverified).

**How a result is checked:** Gaia non-single-star orbits and astrometric excess noise, plus TESS light curves, all public.

**First step:** build the list of ML-validated planets from the NASA Exoplanet Archive. Cross-match it with DR3 RUWE and non-single-star solutions, and get the DR4 queries ready.

**Risks**
- Validation is probabilistic, so a few false positives are expected.
- A high RUWE is not proof of a binary companion.
- The work is crowded on DR4's first day.

**What would kill it:** DR4's own papers flag these hosts.

---

### 5. `bound-replay` (fits Ahraz's exact checking and Doug's race format)
**Question:** Do the certificates behind the crowdsourced records for optimisation constants actually check out?

**Why now**
- Tao's repository lists 117 bound rows. By my tally of the page, 26 bound values across 22 constants carry an asterisk for "minimal" verification ([site](https://teorth.github.io/optimizationproblems/), last entry 17 Oct).
- Submissions are reviewed only for "plausibility and replicability" ([README](https://github.com/teorth/optimizationproblems)).

**Who else is checking**
- C. Toledo replayed certificates for 3b, 3c and 71 in exact arithmetic, which removed one asterisk.
- SqueezeBench checks its own records with two Lean kernels ([arXiv:2610.13461](https://arxiv.org/abs/2610.13461)).

**How a result is checked:** replay each certificate in exact rational or interval arithmetic, with no code shared with the claimant.

**First step:** replay the five easiest asterisked bounds and offer the replays upstream.

**Risks:** low significance per entry; the maintainers may add a checker of their own.

---

### Streams rejected as already well checked
- **Exponent races** (integer and matrix multiplication, 3SUM, APSP, exact DFT): Big O Speedrun runs Comparator checks on 20 problems ([site](https://bigospeedrun.com)), alongside f0's own tracker.
- **Erdős problems:** Bloom's site and his blog post on the OpenAI release, formal-conjectures, and FrontierMath Erdős ([arXiv:2609.25050](https://arxiv.org/pdf/2609.25050)). Tao's AI-contributions wiki stopped updating on 30 Jun 2026 ([wiki](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)). That is a small gap, partly closed by candidate 1.
- **Reproducing ML conference papers:** Hugging Face and alphaXiv covered 2,226 ICML 2026 papers ([blog](https://huggingface.co/blog/icml-2026-open-reproductions)).
- **Economics and political science:** 4,452 economics packages ([NBER w35782](https://www.nber.org/papers/w35782)) and 384 political science papers ([arXiv:2602.16733](https://arxiv.org/abs/2602.16733)).
- **Virtual-cell models:** VCBench ([bioRxiv](https://www.biorxiv.org/content/10.64898/2026.06.18.733146v1.full.pdf)), plus a 2026 empirical comparison and [arXiv:2604.27646](https://arxiv.org/pdf/2604.27646).
- **OpenAI's ten August results:** the Sienicki audit already covers them.
- **AI-claimed new materials:** deferred rather than rejected. Critics are active: Juelsholt on MatterGen ([Materials Horizons 2026](https://pubs.rsc.org/en/content/articlehtml/2026/mh/d6mh00268d)) and the A-Lab correction ([C&EN](https://cen.acs.org/research-integrity/Nature-robot-chemist-paper-corrected/104/web/2026/01)). The key novelty database, ICSD, is paywalled, so an open checker would be weaker.

**Unverified:** the date Palomar opened (secondary source says 18 Aug), whether DPAC will cross-match known planets, and Bloom's exact wording (taken from OfficeChai, not his blog).
