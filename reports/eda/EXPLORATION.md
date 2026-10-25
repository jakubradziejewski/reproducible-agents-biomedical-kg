Exploratory log — not part of the reproducible report; numbers here are as observed on 2026-10-25.

Budget: 15 of `MAX_PROBES = 25` probe queries used (one of them failed and still counts). Every probe's
hypothesis, query and row count is in `probes.jsonl`; results are cached in `data/eda/probes/<slug>.csv`.
Some seeds were answered offline from the already-cached report datasets (`data/eda/*.csv`); those checks
are marked *offline* and cost no probe. Exploration stopped early: the seed list was used up and probes
10-14 found nothing new.

## Offline checks (cached data, no probe)

### id_formats (offline)
- Hypothesis: every label has one identifier format.
- Result: 0 deviating ids in all 11 labels (`UBERON:\d+`, `GO:\d{7}`, `DB\d{5}`, `DOID:\d+`, Entrez integers,
  `N\d{10}`, UMLS `C\d{7}`, MeSH `D\d{6}`). Pathways use two schemes by source: 1,528 `PC7_<n>` and the rest
  `WP<n>_r<rev>`.
- Verdict: *nothing*.

### chromosome_values (offline, followed up by probe 7)
- Hypothesis: `Gene.chromosome` takes only 1-22, X, Y, MT.
- Result: besides the 37 missing values (already in Q5), 18 genes have `X|Y` and 11 have `Un`.
- Verdict: *candidate* (see probe 7).

### zscore_heaping (offline)
- Hypothesis: CuG/CdG `z_score` values heap at particular values or are cut at a threshold.
- Result: no heaping (most frequent rounded value occurs 16 times among 21,102). Both directions are cut at
  |z| = 4.051, but density *rises* away from the cut (284 edges in 4.05-4.1 vs 3,790 in 5-6), so the edges were
  not selected by a plain z threshold alone. Disease log2 fold changes: 13% of DuG/DdG edges have |lfc| < 0.01.
- Verdict: *noted* (the cut-off itself is visible in the Q6 table).

### edgeless_compounds (offline)
- Hypothesis: compounds with no BINDS, TREATS or CAUSES edge are an odd, unexplained group.
- Result: 85 compounds; 14 of them fully isolated (already in B3). Most of the rest are anti-infectives
  (Lymecycline, Cefmenoxime, Tigecycline, Colistin, Imipenem, ...) whose targets are microbial, not human
  genes; 61 of the 85 still have RESEMBLES_CrC edges.
- Verdict: *noted* (expected given a human-gene graph; coverage already in B4).

### degree_outliers (offline)
- Hypothesis: some nodes have a robust z > 10 in one relationship type, beyond the known hubs.
- Result: the outliers are the known ones: kinase inhibitors for BINDS (Sunitinib 132, Bosutinib 104),
  psychoactive drugs for side effects (Pregabalin 839), hypertension for TREATS (68), UBC/APP for INTERACTS.
- Verdict: *nothing* (hub bias is already covered in B3/section 4).

### isolated_genes (offline, surfaced while reading probe 7)
- Hypothesis: the 1,800 isolated genes (B3) are mostly placeholder `LOC` records.
- Result: 1,463 of the 1,800 isolated genes have names starting `LOC`; 1,463 of all 1,548 `LOC` genes are
  isolated. Other patterns are rare among isolated genes (`C<n>orf` 43, `FAM` 21).
- Example by name: `LOC100288966` ("POTE ankyrin domain family member D-like", chromosome `Un`) has degree 0
  (probe 15).
- Verdict: *candidate* -> **promoted** as `loc_placeholder_genes` (modelling artefact).

## Probes

### 1. treat_and_cause
- Hypothesis: some TREATS pairs have the compound also cause a side effect named like one of the disease's
  symptoms (confounding by indication); expect tens.
- Result: 3,157 (compound, disease, symptom) triples covering 637 of the 755 TREATS pairs. Dominated by
  generic symptoms: Nausea 294, Pain 248, Vomiting 242. E.g. Abacavir / AIDS / Nausea.
- Verdict: *noted* — the overlap is driven by base rates of generic symptoms, not a clean signal.

### 2. treat_causes_own_disease
- Hypothesis: some compounds that treat D also "cause" a side effect named D; expect 10-50.
- Result: 61 rows. E.g. Salbutamol / asthma / C0004096, Candesartan / hypertension / C0020538,
  Colchicine / gout / C0018099.
- Verdict: *candidate* (needs a baseline, probe 9).
- Correction (review, fix round 1): this probe matched `toLower(se.name) = d.name`, which lowercases only the
  side-effect name, so the 14 mixed-case disease names could never match. The registered dataset
  `finding_drug_causes_indication` now uses `toLower(se.name) = toLower(d.name)` and adds Crohn's disease
  (1 treating compound causes it) and hepatitis B (3), giving 65 such TREATS edges instead of 61. The
  logged probe and the numbers above are left as observed.

### 3. similar_diseases_no_genes
- Hypothesis: 10-30% of RESEMBLES_DrD pairs share no gene and no symptom.
- Result: only 9 of 543 pairs, mostly involving gene-poor diseases (e.g. bone cancer - tracheal cancer,
  tracheal cancer has 1 gene).
- Verdict: *nothing* (hypothesis refuted).

### 4. anatomy_expr_vs_reg
- Hypothesis: some anatomies have UP/DOWN regulation but no EXPRESSES edges, or vice versa.
- Result: all 36 anatomies with regulation edges also have EXPRESSES and both up and down edges; 161 anatomies
  have no expression at all (coverage already in B4).
- Verdict: *nothing*.

### 5. identical_similarity
- Hypothesis: the 23 RESEMBLES_CrC edges with similarity 1.0 join stereoisomers or duplicate records.
- Result: 22 of 23 share the InChIKey connectivity block (e.g. Citalopram - Escitalopram, Ofloxacin -
  Levofloxacin); Neomycin - Framycetin share the full InChIKey; Cycrimine - Procyclidine is the exception.
- Verdict: *candidate*, not promoted (see conclusion).

### 6. stereo_pairs
- Hypothesis: more compound pairs share an InChIKey skeleton than the 23, some without RESEMBLES edge.
- Result: 24 pairs; 22 linked at similarity 1.0, Omeprazole - Esomeprazole at 0.9403, and Ardeparin -
  Enoxaparin (identical InChIKey) without any RESEMBLES edge.
- Verdict: *noted* (supports probe 5).

### 7. chromosome_values
- Hypothesis: `X|Y` genes are pseudoautosomal; `Un` genes are unplaced loci.
- Result: 29 rows. All 18 `X|Y` genes are known PAR genes (SHOX, CSF2RA, IL3RA, CD99, ... in PAR1; VAMP7,
  SPRY3 in PAR2) with degrees 11-621. All 11 `Un` genes are degree-0 `LOC` records (e.g. LOC100288966).
- Example by name: SHOX has chromosome `X|Y` (probe 15).
- Verdict: *candidate* -> **promoted** as `nonstandard_chromosomes`, narrowed in review fix round 1 to the
  18 `X|Y` genes. The dataset now lists those genes by name and id, and the report sentence gives the count
  and the first two names alphabetically (AKAP17A, ASMT). The 11 `Un` genes were dropped from this
  finding: all of them are isolated `LOC` records and belong under `loc_placeholder_genes`.
- Classification after narrowing: *real biology* still holds. `X|Y` is Entrez Gene's annotation for genes
  that are physically present on both sex chromosomes. Every one of the 18 genes checked by hand (SHOX,
  CSF2RA, IL3RA, CD99, ... in PAR1; VAMP7, SPRY3 in PAR2) is a known pseudoautosomal gene, and none is
  isolated (degrees 11-621), so these are ordinary, well-annotated genes rather than artefacts. The report
  sentence states only what the data shows ("listed on both chromosomes X and Y"). The pseudoautosomal
  explanation was checked by hand, not by code, so it stays here and is not in REPORT.md.

### 8. organ_cancer_localizes
- Hypothesis: some "<organ> cancer" diseases lack a LOCALIZES edge to the same-named anatomy.
- Result: 11 matches; 9 localize correctly; the 2 misses (middle ear cancer, nasal cavity cancer) have no
  LOCALIZES edges at all.
- Verdict: *nothing*.

### 9. own_disease_baseline
- Hypothesis: treating compounds cause a same-named side effect several-fold more often than all compounds.
- Result: 50 diseases share a name with a side effect, 34 of them treated. 61 of the 431 TREATS edges into
  them come from a compound causing the same-named side effect, against 34.2 expected from the all-compound
  rate: 1.8x. Strong for rare side effects (AIDS 4/14 treaters vs 18/1,552 compounds; COPD 3/9 vs 28/1,552),
  absent for common ones (hypertension 17/68 = 25% vs 453/1,552 = 29%; 29% of all compounds "cause"
  hypertension).
- Correction (review, fix round 1): like probe 2, this probe used the asymmetric match
  `toLower(se.name) = d.name` and so missed the mixed-case diseases Crohn's disease (6 treaters, 1 causing,
  15 causers), hepatitis B (4 treaters, 3 causing, 16 causers) and Parkinson's disease (0 treaters, 12
  causers). With `toLower` on both sides (the registered dataset), 53 diseases share a name with a side
  effect, 36 of them treated; 65 of 441 TREATS edges come from a compound causing the same-named side
  effect, against 34.3 expected: 1.9x. The figures above are left as observed.
- Example by name: Salbutamol TREATS asthma and CAUSES side effect `Asthma` (C0004096) (probe 15). Re-checked
  after the fix: the refreshed dataset still has asthma with side effect C0004096 and 11 of 37 treating
  compounds causing it, so the example holds unchanged.
- Verdict: *candidate* -> **promoted** as `drug_causes_indication`. Classified *unexplained*: the pairs mix
  plausible indication leakage from label text mining (SIDER) with real paradoxical or rebound effects
  (e.g. bronchospasm warnings for beta-agonists, rebound hypertension for guanfacine); the graph cannot
  tell them apart.

### 10. nested_disease_names
- Hypothesis: few disease names contain another disease's full name; expect < 10.
- Result: 0 pairs.
- Verdict: *nothing*.

### 11. nested_compound_names (failed)
- Hypothesis: some compound names are another compound's name plus a word (salt/ester entries).
- Result: query error (operator precedence: `STARTS WITH` binds tighter than `+`). Counted against budget.
- Verdict: *nothing* (retried as probe 12).

### 12. nested_compound_names_2
- Hypothesis: as probe 11; expect 10-40 pairs.
- Result: 6 pairs (e.g. Testosterone - Testosterone Propionate, Icosapent - Icosapent ethyl, Estradiol -
  "Estradiol valerate/Dienogest", a combination product stored as one compound).
- Verdict: *noted* (too small to matter).

### 13. pathway_name_dupes
- Hypothesis: the 6 duplicated Pathway names (Q4) come from two sources and overlap only partially.
- Result: 5 are Reactome vs WikiPathways, 1 (Notch Signaling Pathway) is two WikiPathways entries; overlap ranges
  from full (DNA Replication 42 of 42, Striated Muscle Contraction 31 of 31) to partial (Apoptosis 36 shared of
  155 and 84).
- Verdict: *noted* (count already in Q4).

### 14. binds_and_regulates
- Hypothesis: < 2% of BINDS pairs also carry a LINCS up/down edge.
- Result: 65 of the 7,371 BINDS pairs whose compound is in LINCS (0.9%): 45 up, 20 down; 4,200 BINDS pairs have
  a compound with no LINCS edges.
- Verdict: *nothing* (as expected).

### 15. example_checks
- Hypothesis: name lookups for the candidates — Salbutamol treats asthma and causes `Asthma`; SHOX has
  chromosome `X|Y`; LOC100288966 has degree 0.
- Result: all three confirmed (C0004096; `X|Y`; `0 / POTE ankyrin domain family member D-like`).
- Verdict: examples confirmed.

## Conclusion

Four candidates met the quantified / not-covered / example / classification criteria; at most 3 can be promoted.
Promoted (registered as `finding_<slug>` datasets, section 5 of REPORT.md):

1. `drug_causes_indication` — *unexplained*.
2. `nonstandard_chromosomes` (the `X|Y` genes only) — *real biology*.
3. `loc_placeholder_genes` — *modelling artefact*.

Not promoted: `identical_similarity` (22 of 23 similarity-1.0 RESEMBLES_CrC edges join stereoisomers, a
modelling artefact of stereo-blind fingerprints). It is real but small, and its benchmark effect (ties at the top
of a similarity ranking) is already handled by the alphabetical tie-break rule, so it was the weakest of the four.
