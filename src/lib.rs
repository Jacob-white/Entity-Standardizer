use pyo3::prelude::*;
use pyo3::types::PyDict;

const VERSION: &str = env!("CARGO_PKG_VERSION");

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

/// Strip a trailing extension from a single already-split phone segment.
fn strip_extension_single_rs(primary: &str) -> &str {
    let trimmed = primary
        .trim_end_matches(|c: char| matches!(c, '!' | '?' | ',' | ';' | '|' | ' ' | '\t' | '\n' | '\r'))
        .trim_start();
    let lower = trimmed.to_ascii_lowercase();
    for marker in [
        ";ext=", "; ext=", ";isub=", "; isub=", "(ext.", "(ext:", "(ext-", "(ext ", " ext.", " ext:", " ext-", " ext#",
        " ext=", " ext ", " extension", " ext", " xt.", " xt:", " xt-", " xt ", " xt", " x.", " x",
        " #", "ext.", "ext", "xt.", "xt", "x.", "x", "#", ",", ";", "p", "w",
    ] {
        if let Some(idx) = lower.rfind(marker) {
            if matches!(marker, "ext." | "ext" | "xt." | "xt" | "x." | "x" | "#") {
                if idx == 0 || !matches!(lower.as_bytes()[idx - 1], b'0'..=b'9' | b';' | b',' | b'|') {
                    continue;
                }
            } else if matches!(marker, "," | ";" | "p" | "w") {
                if idx == 0 || !lower.as_bytes()[idx - 1].is_ascii_digit() {
                    continue;
                }
            }
            let tail = &lower[idx + marker.len()..];
            let tail_clean = tail.trim_matches(|c: char| {
                matches!(c, ' ' | ')' | '!' | ':' | '-' | '=' | '#' | ',' | ';' | 'p' | 'w')
            });
            let max_ext_len = if matches!(marker, "," | ";" | "p" | "w") {
                7
            } else {
                10
            };
            if !tail_clean.is_empty()
                && tail_clean.len() <= max_ext_len
                && tail_clean.chars().all(|c| c.is_ascii_digit())
            {
                if marker == "," {
                    let base = &trimmed[..idx];
                    let base_digits = base.chars().filter(|c| c.is_ascii_digit()).count();
                    if base_digits < 10 || base.contains(',') {
                        continue;
                    }
                }
                return trimmed[..idx]
                    .trim_end_matches(|c: char| matches!(c, '!' | '?' | ',' | ';' | '|' | '-' | ' ' | '\t' | '\n' | '\r'))
                    .trim();
            }
        }
    }
    let tb = trimmed.as_bytes();
    if tb.len() >= 14
        && tb.len() <= 18
        && matches!(tb[0], b'2'..=b'9')
        && tb[1].is_ascii_digit()
        && tb[2].is_ascii_digit()
        && tb[3] == b'-'
        && matches!(tb[4], b'2'..=b'9')
        && tb[5].is_ascii_digit()
        && tb[6].is_ascii_digit()
        && tb[7] == b'-'
        && tb[8..12].iter().all(|b| b.is_ascii_digit())
    {
        if tb[12] == b'-' && tb[13..].iter().all(|b| b.is_ascii_digit()) {
            return &trimmed[..12];
        }
        if (15..=17).contains(&tb.len()) && tb[12..].iter().all(|b| b.is_ascii_digit()) {
            return &trimmed[..12];
        }
    }
    trimmed
}

/// Return True if a multi-phone segment represents a clean 10- or 11-digit NANP candidate.
fn is_clean_nanp_segment_rs(seg: &str) -> bool {
    let cleaned = strip_extension_single_rs(seg);
    let pure_digits: String = cleaned.chars().filter(|c| c.is_ascii_digit()).collect();
    let digits: String = if pure_digits.len() < 10
        && pure_digits.len() >= 3
        && has_vanity_word_rs(cleaned)
    {
        if let Some(first_digit_idx) = cleaned.find(|c: char| c.is_ascii_digit()) {
            fold_vanity_digits_rs(&cleaned[first_digit_idx..])
                .chars()
                .filter(|c| c.is_ascii_digit())
                .collect()
        } else {
            pure_digits
        }
    } else if cleaned.chars().any(|c| c.is_ascii_alphabetic()) {
        return false;
    } else {
        pure_digits
    };
    let db = digits.as_bytes();
    if db.len() == 10 && matches!(db[0], b'2'..=b'9') && matches!(db[3], b'2'..=b'9') {
        return true;
    }
    db.len() == 11 && db[0] == b'1' && matches!(db[1], b'2'..=b'9') && matches!(db[4], b'2'..=b'9')
}

fn starts_with_extension_marker_rs(after: &str) -> bool {
    if after.starts_with('#') {
        return true;
    }
    for prefix in ["extension", "ext.", "ext", "xt.", "xt", "x.", "x", "isub"] {
        if let Some(rem) = after.strip_prefix(prefix) {
            if rem.starts_with(|c: char| {
                c.is_ascii_digit() || matches!(c, ' ' | '\t' | ':' | '-' | '=' | '#' | '.')
            }) {
                return true;
            }
        }
    }
    false
}

/// If input contains multiple complete phone numbers separated by ';', '/', '|', '&', ',', or whitespace, return the primary phone.
fn split_primary_phone_rs(input: &str) -> &str {
    let bytes = input.as_bytes();
    let mut split_indices = Vec::new();
    for (idx, &b) in bytes.iter().enumerate() {
        if b == b';' || b == b'/' || b == b'&' || b == b'|' {
            let after = input[idx + 1..].trim_start().to_ascii_lowercase();
            if !starts_with_extension_marker_rs(&after) {
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
        let has_alpha1 = p1_trim.chars().any(|c| c.is_ascii_alphabetic());
        if d0 >= 7 && (d1 >= 7 || (bytes[idx0] == b'/' && d0 >= 9 && (1..=6).contains(&d1) && !has_alpha1)) {
            return split_primary_phone_rs(part0.trim());
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
            let a0 = p0.chars().filter(|c| c.is_ascii_alphabetic()).count();
            let d1 = next_seg.chars().filter(|c| c.is_ascii_digit()).count();
            if (d0 >= 7 || (d0 >= 3 && d0 + a0 >= 7 && a0 >= 3)) && d1 >= 7 {
                let p0_sub = split_primary_phone_rs(p0.trim());
                if !is_clean_nanp_segment_rs(p0_sub) {
                    for j in i..comma_indices.len() {
                        let start = comma_indices[j] + 1;
                        let end = if j + 1 < comma_indices.len() {
                            comma_indices[j + 1]
                        } else {
                            input.len()
                        };
                        let alt_sub = split_primary_phone_rs(input[start..end].trim());
                        if is_clean_nanp_segment_rs(alt_sub) {
                            return alt_sub;
                        }
                    }
                }
                return p0_sub;
            }
        }
    }
    let t = input.trim();
    if !t.contains('+')
        && t.chars().filter(|c| c.is_ascii_digit()).count() == 20
        && t.chars()
            .all(|c| c.is_ascii_digit() || matches!(c, ' ' | '-' | '.' | '(' | ')'))
    {
        let mut d_count = 0usize;
        let mut tenth_end = 0usize;
        let mut first_digit = b'0';
        let mut eleventh_digit = b'0';
        for (idx, ch) in t.char_indices() {
            if ch.is_ascii_digit() {
                d_count += 1;
                if d_count == 1 {
                    first_digit = ch as u8;
                } else if d_count == 10 {
                    tenth_end = idx + 1;
                } else if d_count == 11 {
                    eleventh_digit = ch as u8;
                    break;
                }
            }
        }
        if matches!(first_digit, b'2'..=b'9')
            && matches!(eleventh_digit, b'2'..=b'9')
            && t[tenth_end..].starts_with(' ')
        {
            return t[..tenth_end].trim();
        }
    }
    let tb = t.as_bytes();
    if tb.len() >= 20
        && matches!(tb[0], b'2'..=b'9')
        && tb[1].is_ascii_digit()
        && tb[2].is_ascii_digit()
        && tb[3] == b'-'
        && matches!(tb[4], b'2'..=b'9')
        && tb[5].is_ascii_digit()
        && tb[6].is_ascii_digit()
        && tb[7] == b'-'
        && tb[8..12].iter().all(|b| b.is_ascii_digit())
        && tb[12] == b'-'
    {
        let rest = &t[13..];
        let rest_digits = rest.chars().filter(|c| c.is_ascii_digit()).count();
        if rest.chars().all(|c| c.is_ascii_digit() || c == '-') && (7..=10).contains(&rest_digits) {
            return &t[..12];
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
    strip_extension_single_rs(primary)
}

/// Return True if input contains a vanity word or trailing '401k' keypad alias.
fn has_vanity_word_rs(input: &str) -> bool {
    let mut run = 0usize;
    let mut prev_run = 0usize;
    for ch in input.chars() {
        if ch.is_ascii_alphabetic() {
            run += 1;
            if run >= 3 || (prev_run >= 1 && prev_run + run >= 3) {
                return true;
            }
        } else if ch == '-' || ch == ' ' {
            prev_run = run;
            run = 0;
        } else {
            prev_run = 0;
            run = 0;
        }
    }
    input.to_ascii_lowercase().ends_with("401k")
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
            let mut trimmed = no_paren_zero.trim();

            if is_time_range_rs(trimmed) {
                return None;
            }

            // Mirror Python decode_vanity_phone trailing alpha guard:
            // if 10 pure digits precede a 3+ letter alphabetic run, strip the trailing portion.
            let mut digits_before_alpha = 0usize;
            let mut alpha_run = 0usize;
            let mut run_start_idx = 0usize;
            let mut truncate_idx = None;
            for (idx, ch) in trimmed.char_indices() {
                if ch.is_ascii_digit() {
                    digits_before_alpha += 1;
                    alpha_run = 0;
                } else if ch.is_ascii_alphabetic() {
                    if alpha_run == 0 {
                        run_start_idx = idx;
                    }
                    alpha_run += 1;
                    if alpha_run >= 3 && digits_before_alpha >= 10 {
                        truncate_idx = Some(run_start_idx);
                        break;
                    }
                } else {
                    alpha_run = 0;
                }
            }
            if let Some(t_idx) = truncate_idx {
                trimmed = trimmed[..t_idx].trim_end_matches(|c: char| {
                    matches!(c, ' ' | '\t' | '-' | '.' | '/' | ',' | ';' | ':' | '(' | '[' | '{' | '#')
                });
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
                if digits.len() == 11
                    && trimmed.chars().all(|c| c.is_ascii_digit())
                    && [
                        "01", "020", "023", "024", "028", "029", "071", "072", "073", "074",
                        "075", "077", "078", "079",
                    ]
                    .iter()
                    .any(|p| digits.starts_with(p))
                {
                    let nsn = &digits[1..];
                    return Some(format!("+44{nsn}"));
                }
                return None;
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

fn iso2_to_calling_code_rs(iso2: &str) -> Option<&'static str> {
    match iso2.trim().to_ascii_uppercase().as_str() {
        "US" | "CA" | "PR" | "VI" | "GU" | "AS" | "MP" | "BM" | "KY" | "BS" | "BB" | "JM" | "TT" | "DO" | "SX" => Some("1"),
        "RU" | "KZ" => Some("7"),
        "EG" => Some("20"),
        "ZA" => Some("27"),
        "GR" => Some("30"),
        "NL" => Some("31"),
        "BE" => Some("32"),
        "FR" => Some("33"),
        "ES" => Some("34"),
        "HU" => Some("36"),
        "IT" => Some("39"),
        "RO" => Some("40"),
        "CH" => Some("41"),
        "AT" => Some("43"),
        "GB" | "UK" | "JE" | "GG" | "IM" => Some("44"),
        "DK" => Some("45"),
        "SE" => Some("46"),
        "NO" => Some("47"),
        "PL" => Some("48"),
        "DE" => Some("49"),
        "PE" => Some("51"),
        "MX" => Some("52"),
        "AR" => Some("54"),
        "BR" => Some("55"),
        "CL" => Some("56"),
        "CO" => Some("57"),
        "VE" => Some("58"),
        "MY" => Some("60"),
        "AU" => Some("61"),
        "ID" => Some("62"),
        "PH" => Some("63"),
        "NZ" => Some("64"),
        "SG" => Some("65"),
        "TH" => Some("66"),
        "JP" => Some("81"),
        "KR" => Some("82"),
        "VN" => Some("84"),
        "CN" => Some("86"),
        "TR" => Some("90"),
        "IN" => Some("91"),
        "PK" => Some("92"),
        "LK" => Some("94"),
        "IR" => Some("98"),
        "MA" => Some("212"),
        "NG" => Some("234"),
        "KE" => Some("254"),
        "PT" => Some("351"),
        "LU" => Some("352"),
        "IE" => Some("353"),
        "FI" => Some("358"),
        "LT" => Some("370"),
        "UA" => Some("380"),
        "CZ" => Some("420"),
        "HK" => Some("852"),
        "TW" => Some("886"),
        "SA" => Some("966"),
        "AE" => Some("971"),
        "IL" => Some("972"),
        _ => None,
    }
}

#[pyfunction]
fn standardize_batch_with_country_rs(
    inputs: Vec<String>,
    countries: Vec<String>,
    default_calling_code: &str,
) -> Vec<Option<String>> {
    inputs
        .into_iter()
        .enumerate()
        .map(|(i, raw)| {
            let cc = countries
                .get(i)
                .and_then(|c| iso2_to_calling_code_rs(c))
                .unwrap_or(default_calling_code);
            let mut single = standardize_batch_e164_rs(vec![raw], cc);
            single.pop().flatten()
        })
        .collect()
}

#[inline]
fn soundex_code(c: char) -> char {
    match c {
        'B' | 'F' | 'P' | 'V' => '1',
        'C' | 'G' | 'J' | 'K' | 'Q' | 'S' | 'X' | 'Z' => '2',
        'D' | 'T' => '3',
        'L' => '4',
        'M' | 'N' => '5',
        'R' => '6',
        _ => '0',
    }
}

pub fn soundex(token: &str) -> String {
    let clean: Vec<char> = token
        .to_uppercase()
        .chars()
        .filter(|c| c.is_ascii_uppercase())
        .collect();

    let Some(&first) = clean.first() else {
        return String::new();
    };

    let mut code = String::with_capacity(4);
    code.push(first);
    let mut prev_code = soundex_code(first);

    for &c in &clean[1..] {
        let curr = soundex_code(c);
        if curr != '0' {
            if curr != prev_code {
                code.push(curr);
                if code.len() == 4 {
                    break;
                }
            }
            prev_code = curr;
        } else if matches!(c, 'A' | 'E' | 'I' | 'O' | 'U' | 'Y') {
            prev_code = '0';
        }
    }

    while code.len() < 4 {
        code.push('0');
    }
    code
}

#[pyfunction]
pub fn compute_soundex(token: &str) -> String {
    soundex(token)
}

pub fn damerau_levenshtein(s1: &str, s2: &str) -> usize {
    if s1 == s2 {
        return 0;
    }
    let chars1: Vec<char> = s1.chars().collect();
    let chars2: Vec<char> = s2.chars().collect();
    let len1 = chars1.len();
    let len2 = chars2.len();
    if len1 == 0 {
        return len2;
    }
    if len2 == 0 {
        return len1;
    }

    let inf = len1 + len2;
    let mut da: std::collections::HashMap<char, usize> = std::collections::HashMap::new();
    let mut h = vec![vec![0usize; len2 + 2]; len1 + 2];

    h[0][0] = inf;
    for i in 0..=len1 {
        h[i + 1][0] = inf;
        h[i + 1][1] = i;
    }
    for j in 0..=len2 {
        h[0][j + 1] = inf;
        h[1][j + 1] = j;
    }

    for i in 1..=len1 {
        let mut db = 0;
        for j in 1..=len2 {
            let i1 = *da.get(&chars2[j - 1]).unwrap_or(&0);
            let j1 = db;
            let cost = if chars1[i - 1] == chars2[j - 1] {
                db = j;
                0
            } else {
                1
            };

            let deletion = h[i][j + 1] + 1;
            let insertion = h[i + 1][j] + 1;
            let substitution = h[i][j] + cost;
            let transposition = h[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1);

            h[i + 1][j + 1] = deletion.min(insertion).min(substitution).min(transposition);
        }
        da.insert(chars1[i - 1], i);
    }

    h[len1 + 1][len2 + 1]
}

#[pyfunction]
pub fn damerau_levenshtein_distance(s1: &str, s2: &str) -> usize {
    damerau_levenshtein(s1, s2)
}

#[pyfunction]
pub fn normalize_ascii_whitespace_rs(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut last_space = true;
    for ch in s.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch.to_ascii_uppercase());
            last_space = false;
        } else if (ch.is_whitespace() || matches!(ch, ',' | '.' | '-' | '#')) && !last_space {
            out.push(' ');
            last_space = true;
        }
    }
    if out.ends_with(' ') {
        out.pop();
    }
    out
}

#[pyfunction]
pub fn normalize_batch_ascii_rs(inputs: Vec<String>) -> Vec<String> {
    inputs
        .into_iter()
        .map(|s| normalize_ascii_whitespace_rs(&s))
        .collect()
}

#[pyfunction]
pub fn get_engine_name() -> &'static str {
    "Rust_PyO3"
}

#[pyfunction]
pub fn is_native() -> bool {
    true
}

#[pyfunction]
pub fn get_capabilities(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("engine", "Rust_PyO3")?;
    dict.set_item("is_native", true)?;
    dict.set_item("version", VERSION)?;
    dict.set_item("pure_python", false)?;
    dict.set_item(
        "native_functions",
        vec![
            "compute_soundex",
            "damerau_levenshtein_distance",
            "normalize_ascii_whitespace_rs",
            "normalize_batch_ascii_rs",
            "fold_vanity_digits_rs",
            "fold_unicode_digits_rs",
            "extract_digits_rs",
            "damerau_levenshtein_distance_rs",
            "standardize_batch_e164_rs",
            "standardize_batch_with_country_rs",
        ],
    )?;
    Ok(dict)
}

fn register_all_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fold_vanity_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(fold_unicode_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(extract_digits_rs, m)?)?;
    m.add_function(wrap_pyfunction!(damerau_levenshtein_distance_rs, m)?)?;
    m.add_function(wrap_pyfunction!(standardize_batch_e164_rs, m)?)?;
    m.add_function(wrap_pyfunction!(standardize_batch_with_country_rs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_soundex, m)?)?;
    m.add_function(wrap_pyfunction!(damerau_levenshtein_distance, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_ascii_whitespace_rs, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_batch_ascii_rs, m)?)?;
    m.add_function(wrap_pyfunction!(get_engine_name, m)?)?;
    m.add_function(wrap_pyfunction!(is_native, m)?)?;
    m.add_function(wrap_pyfunction!(get_capabilities, m)?)?;
    Ok(())
}

#[pymodule]
fn _phone_standardizer_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    register_all_functions(m)
}

#[pymodule]
fn _address_standardizer_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    register_all_functions(m)
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
                "1800TAXSKI,9097848831".to_string(),
                "7174362144ext25025,7176676902".to_string(),
                "2125551234ext101".to_string(),
                "4155552671ext9999".to_string(),
                "2125551234xt101".to_string(),
                "5853254140,5854358032;2125551234".to_string(),
                "5853254140,5854358032/2125551234".to_string(),
                "5853254140,5854358032|2125551234".to_string(),
                "1,800,555,1212".to_string(),
                "818,985,2000".to_string(),
                "#2125551234".to_string(),
                "2125551234FOOBAR".to_string(),
                "1956468217,8307763662,9564682169".to_string(),
                "212 937 8444 917 363 9568".to_string(),
                "786 244-7346 786 458-8491".to_string(),
                "877-6EN-CORE".to_string(),
                "855-508-401k".to_string(),
                "860-521-401k".to_string(),
                "415-984-1915-1".to_string(),
                "415-984-1915-1921".to_string(),
                "315-627-0474225".to_string(),
                "800-965-2576-949-365-177".to_string(),
                "312-558-9400-800-969-3987".to_string(),
                "212-687-5650-6246633423".to_string(),
                "01212345678".to_string(),
                "02079460912".to_string(),
                "212-555-0199;x123".to_string(),
                "212-555-0199;xt123".to_string(),
                "212-555-0199;xt. 45".to_string(),
                "212-555-0199,x123".to_string(),
                "212-555-0199|x123".to_string(),
                "+298 123456;ext. 45".to_string(),
                "212-555-0199; x123; 415-555-2671".to_string(),
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
                Some("+19097848831".to_string()),
                Some("+17174362144".to_string()),
                Some("+12125551234".to_string()),
                Some("+14155552671".to_string()),
                Some("+12125551234".to_string()),
                Some("+15853254140".to_string()),
                Some("+15853254140".to_string()),
                Some("+15853254140".to_string()),
                Some("+18005551212".to_string()),
                Some("+18189852000".to_string()),
                Some("+12125551234".to_string()),
                Some("+12125551234".to_string()),
                Some("+18307763662".to_string()),
                Some("+12129378444".to_string()),
                Some("+17862447346".to_string()),
                Some("+18776362673".to_string()),
                Some("+18555084015".to_string()),
                Some("+18605214015".to_string()),
                Some("+14159841915".to_string()),
                Some("+14159841915".to_string()),
                Some("+13156270474".to_string()),
                Some("+18009652576".to_string()),
                Some("+13125589400".to_string()),
                Some("+12126875650".to_string()),
                Some("+441212345678".to_string()),
                Some("+442079460912".to_string()),
                Some("+12125550199".to_string()),
                Some("+12125550199".to_string()),
                Some("+12125550199".to_string()),
                Some("+12125550199".to_string()),
                Some("+12125550199".to_string()),
                Some("+298123456".to_string()),
                Some("+12125550199".to_string()),
            ]
        );
    }

    #[test]
    fn test_soundex_standard_names() {
        assert_eq!(soundex("Robert"), "R163");
        assert_eq!(soundex("Rupert"), "R163");
        assert_eq!(soundex("Rubin"), "R150");
        assert_eq!(soundex("Washington"), "W252");
    }

    #[test]
    fn test_soundex_ashcraft_tymczak_pfister() {
        assert_eq!(soundex("Ashcraft"), "A261");
        assert_eq!(soundex("Ashcroft"), "A261");
        assert_eq!(soundex("Tymczak"), "T522");
        assert_eq!(soundex("Pfister"), "P236");
    }

    #[test]
    fn test_soundex_edge_cases() {
        assert_eq!(soundex(""), "");
        assert_eq!(soundex("12345-!@#"), "");
        assert_eq!(soundex("A"), "A000");
        assert_eq!(compute_soundex("Main"), "M500");
    }

    #[test]
    fn test_damerau_levenshtein_address_tokens() {
        assert_eq!(damerau_levenshtein("STREET", "STREET"), 0);
        assert_eq!(damerau_levenshtein("STREET", "STERET"), 1);
        assert_eq!(damerau_levenshtein("AVENUE", "AVNEUE"), 1);
        assert_eq!(damerau_levenshtein("BOULEVARD", "BLVD"), 5);
    }

    #[test]
    fn test_damerau_levenshtein_edge_cases_and_whitespace() {
        assert_eq!(damerau_levenshtein("", ""), 0);
        assert_eq!(damerau_levenshtein("ABC", ""), 3);
        assert_eq!(damerau_levenshtein("", "ABC"), 3);
        assert_eq!(damerau_levenshtein("CA", "AC"), 1);
        assert_eq!(damerau_levenshtein("ABC", "CA"), 2);
        assert_eq!(
            normalize_ascii_whitespace_rs("  123  Main, St. #4B - "),
            "123 MAIN ST 4B"
        );
    }
}


