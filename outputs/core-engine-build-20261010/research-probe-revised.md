# Final revised research-planner comparison

Same four synthetic cases, exact complete contexts and deliberately imperfect interpretation proposals; pinned `gpt-4.1-mini-2025-04-14`. Production ceiling remains 6,500 output tokens. Four calls, no repair calls or provider retries. Exact prompts, schemas, raw outputs, accepted proposals and usage are in `research-probe-revised.json`. Baseline `research-probe.json` is unchanged.

**Result: mixed, with a consequential coverage regression.** The revised planner fixes the social over-plan and removes the unsupported agreement-scope assumption, but drops two requested results and merges others. Source/shape validation accepts all revised outputs; it does not establish completeness or semantic correctness.

| Case | Baseline | Revised | Assessment |
|---|---|---|---|
| Deposit and drive | Three results separately planned; no-send lost; report non-supply became nonexistence | Only deposit recovery planned; drive recovery and client questions absent; no-send still absent | Regression in independent-work coverage. Main outcome preserves non-supply, but enquiry purpose still ambiguously says absence. Client location still becomes assumed jurisdiction. |
| Follow-up and diversion | Explanation and passage review separately planned | Both meanings survive in one work item; ownership remains open, missing plan and no-notice limit preserved | Result identity regresses. No court decision and missing plan risk becoming automatic analysis blockers. |
| Social closing | Model renewed old work; code rejected it for no current support | Model returns empty work with no rejection | Improvement: pending work does not renew itself. |
| Opponent allegation | Two results planned; one constraint assumed the agreement governed the relationship | Both meanings survive in one work item; no agreement-governs assumption; allegation, denial and no-pay limit preserved | Scope improves; result identity regresses. Typical contract clauses and effect of denial are imprecise retrieval targets. |

Requested result meanings retained: **7/7 before, 5/7 after**. Work items: **7 before, 3 after**. The two follow-up/opponent pairs are present but grouped; these counts are not interchangeable. Revised admitted enquiries: **9**. No invented named authority or claimed completed effect was observed. Three substantive outputs still need semantic handling; a clean closing is not evidence for substantive accuracy.

The narrower deposit-only interpretation is deliberately wrong. The original input contains all three requests, so omission demonstrates that including complete context and instructing the planner to ignore earlier errors does not guarantee that it does so. Conversely, the revised planner does reject the false ownership and concealment interpretations in the other cases. This is uneven behaviour, not total inability to use originals.

One model call remains the planner's cost per turn. This comparison added **$0.003785**, with **4,647 input / 1,203 output tokens**. Latencies: 923–4,268 ms, median 3,478 ms; 12,147 ms total. Shared build ledger: **$0.026092 / $5**, 28 physical attempts, no unknown reservations.

Keep the planner as a proposal, not a request ledger or completion authority. The next integrated writer/reviewer check must compare the complete original requests with delivered work, detect omitted independent outcomes and unsupported premises, and preserve valid work. No further isolated tuning or calls were made here. No retrieval, final response, save/reopen, or browser acceptance is established by this probe.

**Implementation decision reported by the parent:** restore the original SYSTEM wording because it retained all seven requested results separately. Preserve both evidence versions and the baseline's unresolved defects; restoration is not semantic acceptance. Later mechanical replay fixes change the file hash, so use the exact saved prompt to identify this comparison. The restored candidate still requires whole-original-context writer/reviewer checks before release.

Baseline evidence SHA-256: `38d173acadf99cf7830a134469a79fde7507cc5a0eced7fd858048d498152497`. Revised production source SHA-256, unchanged during the run: `89ae62b3e8c110eb5c55105048782cbb66ed608922cb4a968632ee20eb413ffa`. One sample per case cannot establish an overall accuracy or false-rejection rate.
