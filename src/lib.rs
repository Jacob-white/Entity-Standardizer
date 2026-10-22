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

/// Compute Optimal String Alignment (Damerau-Levenshtein) distance between two strings.
#[pyfunction]
pub fn damerau_levenshtein_distance_rs(s1: &str, s2: &str) -> usize {
    if s1 == s2 {
        return 0;
    }
    let a: Vec<char> = s1.chars().collect();
    let b: Vec<char> = s2.chars().collect();
    let len1 = a.len();
    let len2 = b.len();
    if len1 == 0 {
        return len2;
    }
    if len2 == 0 {
        return len1;
    }

    let mut dp = vec![vec![0usize; len2 + 1]; len1 + 1];
    for (i, row) in dp.iter_mut().enumerate().take(len1 + 1) {
        row[0] = i;
    }
    for j in 0..=len2 {
        dp[0][j] = j;
    }

    for i in 1..=len1 {
        for j in 1..=len2 {
            let cost = usize::from(a[i - 1] != b[j - 1]);
            let mut best = (dp[i - 1][j] + 1)
                .min(dp[i][j - 1] + 1)
                .min(dp[i - 1][j - 1] + cost);
            if i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1] {
                best = best.min(dp[i - 2][j - 2] + 1);
            }
            dp[i][j] = best;
        }
    }
    dp[len1][len2]
}

/// Return True if input contains a clock time expression like "8:00AM" or "6:00 PM".
fn is_time_range_rs(input: &str) -> bool {
    let bytes = input.as_bytes();
    for (idx, &b) in bytes.iter().enumerate() {
        if b == b':' && idx >= 1 && idx + 2 < bytes.len() {
            if !bytes[idx - 1].is_ascii_digit() {
                continue;
            }
            if !bytes[idx + 1].is_ascii_digit() || !bytes[idx + 2].is_ascii_digit() {
                continue;
            }
            let after_min = &input[idx + 3..].trim_start();
            let lower = after_min.to_ascii_lowercase();
            if lower.starts_with("am") || lower.starts_with("pm") {
                let next_ch = lower.chars().nth(2);
                if next_ch.is_none_or(|c| !c.is_ascii_alphanumeric()) {
                    return true;
                }
            }
        }
    }
    false
}

/// If input contains multiple complete phone numbers separated by ';', '/', '|', '&', or ',', return the primary (first) phone.
fn split_primary_phone_rs(input: &str) -> &str {
    let bytes = input.as_bytes();
    let mut split_indices = Vec::new();
    for (idx, &b) in bytes.iter().enumerate() {
        if b == b';' || b == b'/' || b == b'&' || b == b'|' {
            let after = input[idx + 1..].trim_start().to_ascii_lowercase();
            if !after.starts_with("ext=") && !after.starts_with("isub=") {
                split_indices.push(idx);
            }
        }
    }
    if let Some(&idx0) = split_indices.first() {
        let part0 = &input[..idx0];
        let part1 = if split_indices.len() >= 2 {
            &input[idx0 + 1..split_indices[1]]
        } else {
            &input[idx0 + 1..]
        };
        let p1_trim = part1.trim();
        let d0 = part0.chars().filter(|c| c.is_ascii_digit()).count();
        let d1 = p1_trim.chars().filter(|c| c.is_ascii_digit()).count();
        if d0 >= 7 && (d1 >= 7 || (d0 >= 10 && p1_trim.len() == 4 && d1 == 4)) {
            return part0.trim();
        }
    }
    if input.contains(',') {
        let mut comma_indices = Vec::new();
        for (idx, &b) in bytes.iter().enumerate() {
            if b == b',' {
                comma_indices.push(idx);
            }
        }
        for (i, &cidx) in comma_indices.iter().enumerate() {
            let p0 = &input[..cidx];
            let next_seg = if i + 1 < comma_indices.len() {
                &input[cidx + 1..comma_indices[i + 1]]
            } else {
                &input[cidx + 1..]
            };
            let d0 = p0.chars().filter(|c| c.is_ascii_digit()).count();
            let d1 = next_seg.chars().filter(|c| c.is_ascii_digit()).count();
            if d0 >= 7 && d1 >= 7 {
                return p0.trim();
            }
        }
    }
    input
}

/// Strip a leading URI scheme ("tel:") or conversational label ("Phone 1: ", "Contact: ") before the phone number.
fn strip_leading_label_rs(input: &str) -> &str {
    let mut s = input.trim();
    if let Some(colon_idx) = s.find(':') {
        let prefix = &s[..colon_idx];
        // Strip if it's "tel:" or a short alphabetic label where no '+' appears before ':'
        if colon_idx <= 25
            && !prefix.contains('+')
            && prefix.starts_with(|c: char| c.is_ascii_alphabetic())
        {
            let after_colon = s[colon_idx + 1..].trim();
            if !after_colon.is_empty() && after_colon.chars().any(|c| c.is_ascii_digit()) {
                s = after_colon;
            }
        }
    }
    s
}

/// Strip a trailing extension (e.g. ";ext=402", " ext. 402", " x104", " #104", ",104", "p104", "w104") from a phone string.
fn strip_extension_rs(input: &str) -> &str {
    let primary = split_primary_phone_rs(input);
    let trimmed = primary
        .trim_end_matches(|c: char| matches!(c, '!' | '?' | ',' | ';' | '|' | ' ' | '\t' | '\n' | '\r'))
        .trim_start();
    let lower = trimmed.to_ascii_lowercase();
    for marker in [
        ";ext=", ";isub=", "(ext.", "(ext:", "(ext-", "(ext ", " ext.", " ext:", " ext-", " ext#",
        " ext ", " extension", " ext", " xt.", " xt:", " xt-", " xt ", " xt", " x.", " x", "x.",
        "x", "#", ",", "p", "w",
    ] {
        if let Some(idx) = lower.rfind(marker) {
            if matches!(marker, "x." | "x" | "," | "p" | "w") {
                if idx == 0 || !lower.as_bytes()[idx - 1].is_ascii_digit() {
                    continue;
                }
            }
            let tail = &lower[idx + marker.len()..];
            let tail_clean = tail.trim_matches(|c: char| {
                matches!(c, ' ' | ')' | '!' | ':' | '-' | '#' | ',' | 'p' | 'w')
            });
            let max_ext_len = if matches!(marker, "," | "p" | "w") {
                7
            } else {
                10
            };
            if !tail_clean.is_empty()
                && tail_clean.len() <= max_ext_len
                && tail_clean.chars().all(|c| c.is_ascii_digit())
            {
                return trimmed[..idx]
                    .trim_end_matches(|c: char| matches!(c, '!' | '?' | ',' | ';' | '|' | ' ' | '\t' | '\n' | '\r'))
                    .trim();
            }
        }
    }
    trimmed
}

/// Return True if input contains a run of at least 3 consecutive ASCII alphabetic characters.
fn has_vanity_word_rs(input: &str) -> bool {
    let mut run = 0usize;
    for ch in input.chars() {
        if ch.is_ascii_alphabetic() {
            run += 1;
            if run >= 3 {
                return true;
            }
        } else {
            run = 0;
        }
    }
    false
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
            let no_ext = strip_extension_rs(&folded);
            let no_label = strip_leading_label_rs(no_ext);
            let no_paren_zero = no_label.replace("(0)", "").replace("( 0 )", "");
            let trimmed = no_paren_zero.trim();

            if is_time_range_rs(trimmed) {
                return None;
            }

            // Check if '+' appears before the first ASCII digit
            let mut has_plus = false;
            for ch in trimmed.chars() {
                if ch == '+' {
                    has_plus = true;
                    break;
                }
                if ch.is_ascii_digit() {
                    break;
                }
            }

            // Count pure ASCII digits first; only fold vanity letters if < 10 digits exist and a 3+ letter word is present
            let pure_digits: String = trimmed.chars().filter(|c| c.is_ascii_digit()).collect();
            let digits: String = if pure_digits.len() < 10
                && pure_digits.len() >= 3
                && has_vanity_word_rs(trimmed)
            {
                // Find first digit and fold letters after it
                if let Some(first_digit_idx) = trimmed.find(|c: char| c.is_ascii_digit()) {
                    let after_first = &trimmed[first_digit_idx..];
                    fold_vanity_digits_rs(after_first)
                        .chars()
                        .filter(|c| c.is_ascii_digit())
                        .collect()
                } else {
                    pure_digits
                }
            } else {
                pure_digits
            };

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
            } else if digits.starts_with('0') && digits.len() >= 8 {
                let stripped_trunk = &digits[1..];
                let combined = format!("{default_calling_code}{stripped_trunk}");
                return if combined.len() <= 15 {
                    Some(format!("+{combined}"))
                } else {
                    None
                };
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
    m.add_function(wrap_pyfunction!(damerau_levenshtein_distance_rs, m)?)?;
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
    fn test_damerau_levenshtein() {
        assert_eq!(damerau_levenshtein_distance_rs("4155552671", "4155552671"), 0);
        assert_eq!(damerau_levenshtein_distance_rs("4155552671", "4155552617"), 1);
        assert_eq!(damerau_levenshtein_distance_rs("4155552671", "4155552672"), 1);
    }

    #[test]
    fn test_extract_digits_and_batch() {
        assert_eq!(extract_digits_rs("+1 (415) 555-2671"), "14155552671");
        let out = standardize_batch_e164_rs(
            vec![
                "(415) 555-2671".to_string(),
                "1-212-555-0199".to_string(),
                "+44 (0) 20 7946 0912 ext. 402".to_string(),
                "Phone 1: +44 20 7946 0912,104".to_string(),
                "+1 415-555-2671p104".to_string(),
                "1-800-FLOWERS".to_string(),
                "123".to_string(),
                "8:00AM - 6:00PM".to_string(),
                "919-977-7741 EXT1001".to_string(),
                "804-802-4955X6055".to_string(),
                "(844) PLAN4IT".to_string(),
                "818,985,2OOO         ,,,,,,".to_string(),
                "212-555-1234 / 212-555-5678".to_string(),
                "212-555-1234, 212-555-5678".to_string(),
                "5853254140,5854358032".to_string(),
                "2149237666,5122220140ext7733,6309242400".to_string(),
                "800.366.7266 | ext. 3211".to_string(),
                "6032262004#233,6179472393".to_string(),
            ],
            "1",
        );
        assert_eq!(
            out,
            vec![
                Some("+14155552671".to_string()),
                Some("+12125550199".to_string()),
                Some("+442079460912".to_string()),
                Some("+442079460912".to_string()),
                Some("+14155552671".to_string()),
                Some("+18003569377".to_string()),
                None,
                None,
                Some("+19199777741".to_string()),
                Some("+18048024955".to_string()),
                Some("+18447526448".to_string()),
                Some("+18189852666".to_string()),
                Some("+12125551234".to_string()),
                Some("+12125551234".to_string()),
                Some("+15853254140".to_string()),
                Some("+12149237666".to_string()),
                Some("+18003667266".to_string()),
                Some("+16032262004".to_string()),
            ]
        );
    }
}


