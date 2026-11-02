//! Per-item failure tallying for `CreateItemsResponse`.

use super::{ITEM_STATUS_OK, MAX_FAILURES_TO_REPORT};
use crate::proto::common::commands::ItemCreationResult;

/// Tally per-item outcomes from a `CreateItemsResponse`.
///
/// KiCad returns one `ItemCreationResult` per submitted item; we treat
/// `status.code == ISC_OK` as success and capture the first
/// [`MAX_FAILURES_TO_REPORT`] error messages for the caller. Individual
/// rejections are NOT turned into errors — they are surfaced via the counts
/// so the UI can show them.
///
/// Returns `(items_created, failures, failure_summary)`. The `(code, count)`
/// summary includes all failures even when individual messages are capped;
/// it is sorted by descending count and then ascending code.
pub(crate) fn tally_item_results(
    created_items: &[ItemCreationResult],
) -> (u32, Vec<String>, Vec<(i32, u32)>) {
    let mut items_created: u32 = 0;
    let mut failures: Vec<String> = Vec::new();
    let mut failure_codes: std::collections::BTreeMap<i32, u32> =
        std::collections::BTreeMap::new();
    for (i, result) in created_items.iter().enumerate() {
        let status = result.status.as_ref();
        let code = status.map(|s| s.code).unwrap_or(0);
        if code == ITEM_STATUS_OK {
            items_created += 1;
        } else {
            // Count this rejection for the summary regardless of
            // whether we surface the individual message below.
            *failure_codes.entry(code).or_insert(0) += 1;
            if failures.len() < MAX_FAILURES_TO_REPORT {
                let msg = status
                    .map(|s| s.error_message.clone())
                    .filter(|m| !m.is_empty())
                    .unwrap_or_else(|| "<no error message>".to_string());
                failures.push(format!("item {i}: code={code}: {msg}"));
            }
        }
    }

    let mut failure_summary: Vec<(i32, u32)> = failure_codes.into_iter().collect();
    failure_summary.sort_by(|(code_a, count_a), (code_b, count_b)| {
        count_b.cmp(count_a).then(code_a.cmp(code_b))
    });

    (items_created, failures, failure_summary)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::common::commands::ItemStatus;

    fn item(code: i32, error_message: &str) -> ItemCreationResult {
        ItemCreationResult {
            status: Some(ItemStatus {
                code,
                error_message: error_message.to_string(),
            }),
            item: None,
        }
    }

    #[test]
    fn test_tally_counts_successes_and_failures() {
        let results = vec![
            item(1, ""),              // ISC_OK
            item(7, "no overlap"),    // ISC_INVALID_DATA
            item(2, "bad type"),      // ISC_INVALID_TYPE
            item(1, ""),              // ISC_OK
        ];
        let (created, failures, summary) = tally_item_results(&results);
        assert_eq!(created, 2, "2 ISC_OK items");
        assert_eq!(failures.len(), 2, "2 rejections surfaced");
        assert!(failures[0].contains("code=7"));
        assert!(failures[0].contains("no overlap"));
        assert!(failures[1].contains("code=2"));
        assert_eq!(summary, vec![(2, 1), (7, 1)], "sorted by count desc, code asc");
    }

    #[test]
    fn test_tally_groups_by_code_and_sorts_count_descending() {
        let results: Vec<ItemCreationResult> = vec![
            item(2, "a"),
            item(7, "b"),
            item(7, "c"),
            item(7, "d"),
            item(7, "e"),
            item(1, ""),
        ];
        let (created, failures, summary) = tally_item_results(&results);
        assert_eq!(created, 1);
        assert_eq!(failures.len(), 5);
        assert_eq!(summary, vec![(7, 4), (2, 1)], "most frequent failure first");
    }

    #[test]
    fn test_tally_caps_surfaced_failures_but_summary_stays_complete() {
        // MAX_FAILURES_TO_REPORT (1000) bounds `failures`; the summary is
        // still computed from every item.
        let mut results: Vec<ItemCreationResult> = (0..1500)
            .map(|_| item(7, "rejected"))
            .collect();
        results.push(item(1, ""));
        let (created, failures, summary) = tally_item_results(&results);
        assert_eq!(created, 1);
        assert_eq!(failures.len(), MAX_FAILURES_TO_REPORT);
        assert_eq!(summary, vec![(7, 1500)]);
    }

    #[test]
    fn test_tally_missing_status_is_a_failure() {
        // A result with no `status` counts as a non-OK item (code 0) and
        // surfaces a placeholder message.
        let results = vec![ItemCreationResult {
            status: None,
            item: None,
        }];
        let (created, failures, summary) = tally_item_results(&results);
        assert_eq!(created, 0);
        assert_eq!(failures, vec!["item 0: code=0: <no error message>".to_string()]);
        assert_eq!(summary, vec![(0, 1)]);
    }
}
