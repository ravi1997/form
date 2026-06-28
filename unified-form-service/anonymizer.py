import re

class DataAnonymizer:
    # Compile regex patterns for PII scrubbing
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
    CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    @classmethod
    def scrub_text(cls, text_str):
        """
        Scrubs common PII patterns from free-form text.
        """
        if not isinstance(text_str, str):
            return text_str

        scrubbed = text_str
        scrubbed = cls.EMAIL_REGEX.sub("[EMAIL_MASKED]", scrubbed)
        scrubbed = cls.PHONE_REGEX.sub("[PHONE_MASKED]", scrubbed)
        scrubbed = cls.CREDIT_CARD_REGEX.sub("[CARD_MASKED]", scrubbed)
        scrubbed = cls.SSN_REGEX.sub("[SSN_MASKED]", scrubbed)
        return scrubbed

    @classmethod
    def anonymize_answers(cls, answers, sensitive_fields):
        """
        Scrubs sensitive fields. Additionally scrubs free-form text fields.
        """
        anonymized = dict(answers)
        for field in sensitive_fields:
            if field in anonymized:
                val = anonymized[field]
                if isinstance(val, str):
                    anonymized[field] = "[ANONYMIZED]"
                elif isinstance(val, (int, float)):
                    anonymized[field] = 0
                else:
                    anonymized[field] = "[ANONYMIZED]"
        
        # Scrub all other string fields just in case they contain PII in comments
        for k, v in anonymized.items():
            if isinstance(v, str) and k not in sensitive_fields:
                anonymized[k] = cls.scrub_text(v)

        return anonymized
