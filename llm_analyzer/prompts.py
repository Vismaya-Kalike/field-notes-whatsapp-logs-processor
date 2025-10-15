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

    return f"""You are analyzing field notes from a learning facilitator named {facilitator_name}. The facilitator works with oppressed communities and creates after school learning spaces with a view to build agency. Spaces are designed to be safe, open, joyful and self-determined where learners can make their own decisions. 

    CONTEXT: The facilitator has shared photos as well as some field notes. Since facilitators often prefer sending images over text, the visual content is crucial for understanding their work.

    INSTRUCTIONS:
    - Analyze both the images and text messages to understand what is happening at the learning center
    - Observe if the learning center is safe, open, joyful and self-determined
    - Make a note if there is play happening in the learning centers
    - Check if the learning center is different from school like spaces
    - The images show real field work activities - describe what you see and avoid making assumptions
    - Create a comprehensive field work report based on visual evidence and text notes
    - Pay special attention to the visual documentation as it's the primary way this facilitator communicates their work

    TEXT MESSAGES AND FIELD NOTES:
    {field_notes_text}

    IMAGES PROVIDED: {images_count} work-related photos showing field activities

    Write this as a professional field work assessment report that recognizes the visual documentation as the primary evidence of the facilitator's work and impact. Don't make up any details and don't add any details that are not in the text messages or images. Don't include the messages and photos in the report. You don't have to describe each photo. You don't need to include the purpose or details about the organisation. It's okay if the report is short and doesn't have a lot of details. Do not include any title or date in the report."""


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
