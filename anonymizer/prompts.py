"""
Prompts for the name anonymization system
"""

def get_name_detection_prompt(text: str) -> str:
    """
    Generate the prompt for AI-based name detection and anonymization

    Args:
        text: The text to analyze for children's names

    Returns:
        The formatted prompt for the AI model
    """
    return f"""You are helping to anonymize children's names in educational field reports for privacy protection.

Please analyze the following text VERY CAREFULLY and identify ALL children's names (first names only). This includes:
- Names of any length (2+ characters)
- Names in English, Hindi, Kannada, Tamil, Telugu, Malayalam, or any Indian language
- Nicknames and shortened names (like "Anu", "Ravi", "Jo")
- Names that might be spelled phonetically or with variations
- Names mentioned in any context (stories, examples, direct references)
- Names in grammatically imperfect text (like "his name mailari" or "sumathi is good")
- Names that may appear multiple times in the text

For each child's name you find, generate an appropriate alternate name that:
1. Maintains the EXACT same gender (if clear from context, otherwise keep gender-neutral)
2. Retains the EXACT same cultural/linguistic identity (e.g., Kannada name → Kannada name, Tamil → Tamil, Hindi → Hindi)
3. Preserves the same religious/traditional background (e.g., Hindu names stay Hindu, Muslim names stay Muslim, Christian names stay Christian)
4. Maintains similar phonetic structure and length
5. Is sufficiently different to protect privacy but keeps cultural authenticity
6. Has similar meaning or cultural significance when possible

Text to analyze:
"{text}"

IMPORTANT INSTRUCTIONS:
- Scan the ENTIRE text thoroughly - don't miss any names
- Include names even if they appear with common words around them
- Be very thorough - missing a name compromises privacy
- Only exclude obvious non-names (places, subjects, days, etc.)
- Focus on first names of children in educational contexts

Respond ONLY with a JSON object where keys are the original names and values are the alternate names. If no children's names are found, respond with an empty JSON object {{}}.

Example format (maintaining gender, culture, and religion):
{{"Aarav": "Arjun", "Priya": "Pooja", "Ravi": "Rohit", "Ananya": "Anjali", "Mohammed": "Ibrahim", "Fatima": "Ayesha", "John": "David", "Mary": "Sarah", "Lakshmi": "Saraswati", "Krishna": "Rama"}}

CRITICAL: Each replacement name MUST belong to the same cultural, linguistic, and religious tradition as the original name."""