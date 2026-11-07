# Settings

Edit badge network, GitHub profile, contact, timezone, and backlight settings.

## Usage

Use the direction controls and Select to edit the six standard values in `/secrets.py`, contact details used by the badge and Contacts apps, and the backlight. Region cycles through the supported Wi-Fi regions, and timezone is limited to GMT-12 through GMT+14. Existing values require confirmation before they can be overridden or cleared; clearing `REGION` and `TIMEZONE` restores `eu` and `0`.

Wi-Fi passwords are masked. GitHub tokens show only their last four characters (shorter tokens are fully masked); use a fine-grained, read-only token. Changes are saved through a temporary file and atomic rename. Restart when prompted after changing Wi-Fi or region settings.

On hardware, the first save copies `/system/secrets.py` to a writable `/secrets.py` override and preserves the other settings. Subsequent edits update that override, not the USB disk's original file; both files may contain plaintext credentials. If saving fails, the current value is not changed. The simulator uses its own settings storage.
