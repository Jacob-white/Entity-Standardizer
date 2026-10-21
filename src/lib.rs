use pyo3::prelude::*;

/// Map an ASCII letter (A-Z, a-z) to its ITU-T E.161 telephone keypad digit.
#[inline]
fn e161_char(ch: char) -> char {
    match ch.to_ascii_uppercase() {
        'A' | 'B' | 'C' => '2',
        'D' | 'E' | 'F' => '3',
        'G' | 'H' | 'I' => '4',
        'J' | 'K' | 'L' => '5',
        'M' | 'N' | 'O' => '6',
        'P' | 'Q' | 'R' | 'S' => '7',
        'T' | 'U' | 'V' => '8',
        'W' | 'X' | 'Y' | 'Z' => '9',
        _ => ch,
    }
}

/// Fold a single Unicode numeral or full-width telephony punctuation character to ASCII.
#[inline]
fn fold_unicode_char(ch: char) -> char {
    let code = ch as u32;
    // Full-width digits '０'..'９' (0xFF10..=0xFF19)
    if (0xFF10..=0xFF19).contains(&code) {
        return char::from_u32(b'0' as u32 + (code - 0xFF10)).unwrap_or(ch);
    }
    // Arabic-Indic digits (0x0660..=0x0669)
    if (0x0660..=0x0669).contains(&code) {
        return char::from_u32(b'0' as u32 + (code - 0x0660)).unwrap_or(ch);
    }
    // Eastern Arabic-Indic digits (0x06F0..=0x06F9)
    if (0x06F0..=0x06F9).contains(&code) {
        return char::from_u32(b'0' as u32 + (code - 0x06F0)).unwrap_or(ch);
    }
    // Devanagari digits (0x0966..=0x096F)
    if (0x0966..=0x096F).contains(&code) {
        return char::from_u32(b'0' as u32 + (code - 0x0966)).unwrap_or(ch);
    }
    match ch {
        '＋' => '+',
        '－' | '–' | '—' | '−' | '‑' => '-',
        '（' => '(',
        '）' => ')',
        _ => ch,
    }
}

/// Fold ASCII letters in a string to ITU-T E.161 digits.
#[pyfunction]
pub fn fold_vanity_digits_rs(input: &str) -> String {
    input.chars().map(e161_char).collect()
}

/// Fold non-ASCII Unicode numerals and full-width punctuation to ASCII, returning (folded, changed).
#[pyfunction]
pub fn fold_unicode_digits_rs(input: &str) -> (String, bool) {
    let mut out = String::with_capacity(input.len());
    let mut changed = false;
    for ch in input.chars() {
        let mapped = fold_unicode_char(ch);
        if mapped != ch {
            changed = true;
        }
        out.push(mapped);
    }
    (out, changed)
}

/// Extract ASCII digits ('0'..'9') from an input string in a single pass.
#[pyfunction]
pub fn extract_digits_rs(input: &str) -> String {
    input.chars().filter(|c| c.is_ascii_digit()).collect()
}

/// High-throughput batch E.164 normalizer for raw phone strings.
#[pyfunction]
pub fn standardize_batch_e164_rs(
    inputs: Vec<String>,
    default_calling_code: &str,
) -> Vec<Option<String>> {
    inputs
        .into_iter()
        .map(|raw| {
            let (folded, _) = fold_unicode_digits_rs(&raw);
            let trimmed = folded.trim();
            let has_plus = trimmed.starts_with('+');
            let digits: String = trimmed.chars().filter(|c| c.is_ascii_digit()).collect();
            if digits.len() < 7 || digits.len() > 15 {
                return None;
            }
            if has_plus {
                return Some(format!("+{digits}"));
            }
            if default_calling_code == "1" {
                if digits.len() == 10 {
                    return Some(format!("+1{digits}"));
                }
                if digits.len() == 11 && digits.starts_with('1') {
                    return Some(format!("+{digits}"));
                }
            }
            let combined = format!("{default_calling_code}{digits}");
            if combined.len() <= 15 {
                Some(format!("+{combined}"))
            } else {
                None
            }
        })
        .collect()
}

#[pymodule]
fn _phone_standardizer_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fold_vanity_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(fold_unicode_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(extract_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(standardize_batch_e164_rs, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fold_vanity_digits() {
        assert_eq!(fold_vanity_digits_rs("1-800-FLOWERS"), "1-800-3569377");
        assert_eq!(fold_vanity_digits_rs("TAX-HELP"), "829-4357");
    }

    #[test]
    fn test_fold_unicode_digits() {
        let (folded, changed) = fold_unicode_digits_rs("＋８１ ３-１２３４-５６７８");
        assert!(changed);
        assert_eq!(folded, "+81 3-1234-5678");
        let (same, ch2) = fold_unicode_digits_rs("+1 415-555-2671");
        assert!(!ch2);
        assert_eq!(same, "+1 415-555-2671");
    }

    #[test]
    fn test_extract_digits_and_batch() {
        assert_eq!(extract_digits_rs("+1 (415) 555-2671"), "14155552671");
        let out = standardize_batch_e164_rs(
            vec![
                "(415) 555-2671".to_string(),
                "1-212-555-0199".to_string(),
                "+44 20 7946 0912".to_string(),
                "123".to_string(),
            ],
            "1",
        );
        assert_eq!(
            out,
            vec![
                Some("+14155552671".to_string()),
                Some("+12125550199".to_string()),
                Some("+442079460912".to_string()),
                None,
            ]
        );
    }
}
