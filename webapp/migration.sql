-- Run this once against your existing Income_Expense_Project database.
-- Adds website login capability to your existing Users table.
--
-- Username keeps working exactly as it does today (freeform display name,
-- collected first, no uniqueness requirement).
-- LoginID is new: a separate, unique field used only for website login.

ALTER TABLE Users ADD LoginID NVARCHAR(255) NULL;
ALTER TABLE Users ADD PasswordHash NVARCHAR(255) NULL;

-- Enforce uniqueness on LoginID, but allow it to stay NULL for users who
-- only ever use the Telegram bot's logging feature and never finish
-- (or never need) website signup.
CREATE UNIQUE INDEX UX_Users_LoginID ON Users(LoginID) WHERE LoginID IS NOT NULL;

-- Notes:
-- - Username: display name only now, not used for login, no uniqueness needed.
-- - LoginID: the unique credential checked by the bot during /start and
--   used to log into the website.
-- - PasswordHash: bcrypt hash, set by the bot once LoginID is confirmed unique.
