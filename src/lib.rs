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

/// Fold ASCII letters in a string to ITU-T E.161 digits.
#[pyfunction]
pub fn fold_vanity_digits_rs(input: &str) -> String {
    input.chars().map(e161_char).collect()
}

#[pymodule]
fn _phone_standardizer_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fold_vanity_digits_rs, m)?)?;
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
}
