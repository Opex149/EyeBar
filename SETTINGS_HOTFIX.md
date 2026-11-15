# Settings window hotfix

Fixed `AttributeError: 'NoneType' object has no attribute 'setText'` in `SettingsDialog.retranslate()`.

Root cause: `QFormLayout.labelForField()` can return `None` for rows initially added with an empty string label. The dialog now creates and retains explicit `QLabel` objects for appearance, general, and launcher rows, and updates those labels directly during translation. This also prevents the same failure in the other two settings sections.

Validation: Python syntax compilation passed. GUI runtime validation requires PyQt6 on Windows.
