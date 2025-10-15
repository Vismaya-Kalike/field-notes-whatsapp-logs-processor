"""
Prompts for the LLM analysis system
"""


def get_comprehensive_analysis_prompt(facilitator_name: str, field_notes: list, images_count: int) -> str:
    """
    Generate the main analysis prompt for image and text analysis

    Args:
        facilitator_name: Name of the facilitator
        field_notes: List of formatted field notes with timestamps
        images_count: Number of images being analyzed

    Returns:
        The formatted prompt for comprehensive analysis
    """
    field_notes_text = '\n'.join(
        field_notes) if field_notes else 'Limited text messages - analysis should focus primarily on visual documentation.'

    return f"""You are analyzing field reports from a teacher/social worker named {facilitator_name} who works with Vismaya Kalike, a social service organization in India.

    CONTEXT: This person shares photos of their work activities, teaching sessions, community outreach, and field notes about their daily work with students and community members. Since facilitators often prefer sending images over text, the visual content is crucial for understanding their work.

    INSTRUCTIONS:
    - Analyze both the images and text messages to understand what activities this person is doing
    - Focus on educational activities, community work, social services, and teaching-related content visible in the images
    - The images show real field work activities - describe what you see in terms of educational impact
    - Create a comprehensive field work report based on visual evidence and text notes
    - Pay special attention to the visual documentation as it's the primary way this facilitator communicates their work

    TEXT MESSAGES AND FIELD NOTES:
    {field_notes_text}

    IMAGES PROVIDED: {images_count} work-related photos showing field activities

    Based on the visual evidence and text data, please provide a comprehensive field work analysis report covering:

    1. **Visual Documentation Analysis**: What activities, teaching sessions, and community work are visible in the images?
    2. **Educational Impact**: What evidence of learning, student engagement, or educational outcomes can you observe?
    3. **Community Engagement**: How is the facilitator interacting with students, parents, or community members?
    4. **Work Patterns and Methods**: What teaching methods, materials, or approaches are visible?
    5. **Overall Assessment**: Based on the visual and text evidence, how would you assess this facilitator's contributions to ViKa's mission?

    Write this as a professional field work assessment report that recognizes the visual documentation as the primary evidence of the facilitator's work and impact. Also write this as the facilitator would be writing it to the outside world. Don't make up any details and don't add any details that are not in the text messages or images. It's okay if the report is short and doesn't have a lot of details."""


def get_text_only_analysis_prompt(facilitator_name: str, field_notes: list, images_count: int) -> str:
    """
    Generate the fallback prompt for text-only analysis

    Args:
        facilitator_name: Name of the facilitator
        field_notes: List of formatted field notes with timestamps
        images_count: Number of images (for context)

    Returns:
        The formatted prompt for text-only analysis
    """
    field_notes_text = '\n'.join(
        field_notes) if field_notes else 'No substantive field notes found in text messages.'

    return f"""You are analyzing field reports from a teacher/social worker named {facilitator_name} who works with ViKa, a social service organization in India.

    CONTEXT: This person shares photos of their work activities, teaching sessions, community outreach, and field notes about their daily work with students and community members.

    FIELD NOTES AND MESSAGES:
    {field_notes_text}

    IMAGES PROVIDED: {images_count} work-related photos (privacy-filtered, visual analysis not available)

    Based on this data, please provide a field work analysis report covering:
    1. Educational/teaching activities observed (if any mentioned in text)
    2. Community outreach or social service work (if any mentioned)
    3. Work patterns and contributions to ViKa organization
    4. Impact and activities based on the documentation provided

    Write this as a professional field work assessment report focusing on their contributions to education and social services."""


def format_image_caption(image_count: int, caption: str) -> str:
    """
    Format image caption for inclusion in analysis

    Args:
        image_count: Number of the image (for labeling)
        caption: The caption text

    Returns:
        Formatted caption text
    """
    return f"Caption for image {image_count}: {caption}"
