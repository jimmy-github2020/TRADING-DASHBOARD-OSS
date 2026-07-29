ALTER TABLE notification_settings
  ADD COLUMN IF NOT EXISTS market_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS price_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS technical_alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS summary_frequency VARCHAR(20) NOT NULL DEFAULT 'morning';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'notification_settings_summary_frequency_check'
  ) THEN
    ALTER TABLE notification_settings
      ADD CONSTRAINT notification_settings_summary_frequency_check
      CHECK (summary_frequency IN ('off', 'daily', 'morning', 'evening'));
  END IF;
END $$;
