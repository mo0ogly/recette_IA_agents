//! Scoring: aggregate check results into per-bloc and global scores plus a
//! human verdict. N/A checks are excluded and the bloc is renormalized.

use serde::Serialize;

use crate::model::{CheckResult, Verdict};

/// Nominal maximum points per bloc (sums to 44).
fn bloc_max(bloc: char) -> f64 {
    match bloc {
        'A' | 'B' | 'C' => 10.0,
        'D' | 'F' => 5.0,
        'E' => 4.0,
        _ => 0.0,
    }
}

/// Per-bloc score breakdown.
#[derive(Debug, Serialize)]
pub struct BlocScore {
    /// Bloc letter.
    pub bloc: char,
    /// Awarded points (0..=max), 0 when no applicable checks.
    pub score: f64,
    /// Maximum points for this bloc when it has applicable checks, else 0.
    pub max: f64,
    /// Number of applicable (non-N/A) checks.
    pub applicable: usize,
    /// Number of passing checks.
    pub passed: usize,
}

/// Full scoring report.
#[derive(Debug, Serialize)]
pub struct ScoreReport {
    /// Per-bloc breakdown (A, B, C, D, E, F order).
    pub blocs: Vec<BlocScore>,
    /// Sum of awarded points.
    pub global: f64,
    /// Sum of maxima for blocs that had applicable checks.
    pub global_max: f64,
    /// Global score normalized to the nominal /44 scale.
    pub normalized_44: f64,
    /// Count of failed critical checks.
    pub critical_fails: usize,
    /// True if any bloc E (R17) check failed.
    pub e_fail: bool,
    /// True if any bloc F (invariant) check failed.
    pub f_violation: bool,
    /// Human-readable verdict.
    pub verdict: String,
}

impl ScoreReport {
    /// True if the run meets `min_score` (on the /44 scale) with no blocking failure.
    pub fn passes(&self, min_score: u32) -> bool {
        self.critical_fails == 0
            && !self.e_fail
            && !self.f_violation
            && self.normalized_44 >= f64::from(min_score)
    }
}

/// Compute the scoring report from all check results.
pub fn score(results: &[CheckResult]) -> ScoreReport {
    let mut blocs = Vec::new();
    let mut global = 0.0;
    let mut global_max = 0.0;

    for bloc in ['A', 'B', 'C', 'D', 'E', 'F'] {
        let in_bloc: Vec<&CheckResult> = results.iter().filter(|r| r.bloc == bloc).collect();
        let applicable = in_bloc.iter().filter(|r| r.verdict != Verdict::Na).count();
        let passed = in_bloc
            .iter()
            .filter(|r| r.verdict == Verdict::Pass)
            .count();
        let max = bloc_max(bloc);

        let (score, counted_max) = if applicable == 0 {
            (0.0, 0.0)
        } else {
            #[allow(clippy::cast_precision_loss)]
            let s = (passed as f64 / applicable as f64) * max;
            (s, max)
        };

        global += score;
        global_max += counted_max;
        blocs.push(BlocScore {
            bloc,
            score,
            max: counted_max,
            applicable,
            passed,
        });
    }

    let normalized_44 = if global_max > 0.0 {
        global / global_max * 44.0
    } else {
        0.0
    };
    let critical_fails = results.iter().filter(|r| r.is_critical_fail()).count();
    let e_fail = results
        .iter()
        .any(|r| r.bloc == 'E' && r.verdict == Verdict::Fail);
    let f_violation = results
        .iter()
        .any(|r| r.bloc == 'F' && r.verdict == Verdict::Fail);

    let verdict = verdict_text(normalized_44, critical_fails, e_fail, f_violation);

    ScoreReport {
        blocs,
        global,
        global_max,
        normalized_44,
        critical_fails,
        e_fail,
        f_violation,
        verdict,
    }
}

/// Map a normalized score and blocking flags to the command's verdict strings.
fn verdict_text(
    normalized_44: f64,
    critical_fails: usize,
    e_fail: bool,
    f_violation: bool,
) -> String {
    if critical_fails > 0 || e_fail || f_violation {
        return "NE PAS INTEGRER. Refonte necessaire.".to_string();
    }
    if normalized_44 >= 39.0 {
        "Pret pour integration.".to_string()
    } else if normalized_44 >= 30.0 {
        "Corrections requises avant integration.".to_string()
    } else {
        "NE PAS INTEGRER. Refonte necessaire.".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Severity;

    #[test]
    fn na_checks_are_excluded_from_max() {
        let results = vec![
            CheckResult::pass("A1", "x", 'A', Severity::Critical),
            CheckResult::na("E1", "y", 'E', Severity::Critical, "manual"),
        ];
        let report = score(&results);
        let bloc_e = report
            .blocs
            .iter()
            .find(|b| b.bloc == 'E')
            .expect("bloc E present");
        assert_eq!(bloc_e.max, 0.0, "all-N/A bloc contributes 0 to max");
        assert_eq!(bloc_e.applicable, 0);
    }

    #[test]
    fn critical_fail_forces_blocking_verdict() {
        let results = vec![CheckResult::fail(
            "A1",
            "x",
            'A',
            Severity::Critical,
            Vec::new(),
        )];
        let report = score(&results);
        assert_eq!(report.critical_fails, 1);
        assert!(!report.passes(0), "a critical fail never passes");
        assert!(report.verdict.contains("NE PAS INTEGRER"));
    }

    #[test]
    fn all_pass_reaches_full_normalized_score() {
        let results = vec![
            CheckResult::pass("A1", "x", 'A', Severity::Critical),
            CheckResult::pass("B1", "y", 'B', Severity::Critical),
        ];
        let report = score(&results);
        assert!(
            (report.normalized_44 - 44.0).abs() < 1e-9,
            "all-pass normalizes to 44"
        );
        assert!(report.passes(39));
    }
}
