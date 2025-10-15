#!/usr/bin/env python3
"""
Photo filtering system for WhatsApp messages.
Filters out photos with clearly identifiable faces for privacy protection.
"""

import os
import shutil
from typing import List, Dict, Any, Tuple
from face_detection.face_detector import is_image_safe_for_display, batch_analyze_images
from face_detection.constants import PRIVACY_KEYWORDS, SUPPORTED_FORMATS

def filter_messages_by_privacy(messages: List[Dict[str, Any]],
                              media_dir: str = "whatsapp_data",
                              strict_mode: bool = False,
                              ultra_conservative: bool = True) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Filter WhatsApp messages to remove those with clearly identifiable faces.

    Args:
        messages (List[Dict]): List of message dictionaries
        media_dir (str): Directory containing media files
        strict_mode (bool): If True, removes any image with faces detected
        ultra_conservative (bool): If True, uses much stricter face detection criteria

    Returns:
        Tuple containing:
        - safe_messages: Messages safe to display publicly
        - filtered_messages: Messages that were filtered out
        - analysis_report: Summary of filtering results
    """

    safe_messages = []
    filtered_messages = []

    analysis_report = {
        'total_messages': len(messages),
        'messages_with_attachments': 0,
        'image_attachments': 0,
        'images_analyzed': 0,
        'safe_images': 0,
        'filtered_images': 0,
        'analysis_errors': 0,
        'filtering_reasons': {},
        'processing_errors': []
    }

    # Image file extensions to check
    image_extensions = SUPPORTED_FORMATS

    for message in messages:
        # Always count messages with attachments
        if message.get('has_attachment', False):
            analysis_report['messages_with_attachments'] += 1

        # Check if message has an image attachment
        if (message.get('has_attachment', False) and
            message.get('attachment_filename')):

            filename = message['attachment_filename']

            # Check if it's an image file
            if any(filename.lower().endswith(ext) for ext in image_extensions):
                analysis_report['image_attachments'] += 1

                # Full path to the image
                image_path = os.path.join(media_dir, filename)

                try:
                    # Analyze the image for privacy concerns
                    analysis_report['images_analyzed'] += 1
                    safety_result = is_image_safe_for_display(image_path, strict_mode, ultra_conservative)

                    if safety_result['is_safe']:
                        # Image is safe - keep the message
                        safe_messages.append(message)
                        analysis_report['safe_images'] += 1
                    else:
                        # Image has privacy concerns - filter it out
                        filtered_messages.append({
                            **message,
                            'filter_reason': safety_result['reason'],
                            'face_analysis': safety_result['face_info']
                        })
                        analysis_report['filtered_images'] += 1

                        # Track filtering reasons
                        reason = safety_result['reason']
                        analysis_report['filtering_reasons'][reason] = \
                            analysis_report['filtering_reasons'].get(reason, 0) + 1

                except Exception as e:
                    # Error analyzing image - err on side of caution and filter it
                    analysis_report['analysis_errors'] += 1
                    analysis_report['processing_errors'].append({
                        'filename': filename,
                        'error': str(e)
                    })

                    filtered_messages.append({
                        **message,
                        'filter_reason': f'Analysis error: {str(e)}',
                        'face_analysis': None
                    })
            else:
                # Non-image attachment - keep the message
                safe_messages.append(message)
        else:
            # No attachment or not an image - keep the message
            safe_messages.append(message)

    return safe_messages, filtered_messages, analysis_report

def create_privacy_report(analysis_report: Dict, sender_name: str = "Unknown") -> str:
    """
    Create a human-readable privacy filtering report.

    Args:
        analysis_report (Dict): Analysis results from filter_messages_by_privacy
        sender_name (str): Name of the sender

    Returns:
        str: Formatted report
    """

    report = f"""
🔒 Privacy Filtering Report for {sender_name}
{'=' * 60}

📊 Summary:
  Total messages: {analysis_report['total_messages']}
  Messages with attachments: {analysis_report['messages_with_attachments']}
  Image attachments: {analysis_report['image_attachments']}

🔍 Analysis Results:
  Images analyzed: {analysis_report['images_analyzed']}
  ✅ Safe to display: {analysis_report['safe_images']}
  ❌ Filtered out: {analysis_report['filtered_images']}
  ⚠️  Analysis errors: {analysis_report['analysis_errors']}

"""

    if analysis_report['images_analyzed'] > 0:
        safety_rate = (analysis_report['safe_images'] / analysis_report['images_analyzed']) * 100
        report += f"🛡️  Privacy safety rate: {safety_rate:.1f}%\n\n"

    if analysis_report['filtering_reasons']:
        report += "📝 Filtering Reasons:\n"
        for reason, count in analysis_report['filtering_reasons'].items():
            report += f"  • {reason}: {count} image(s)\n"
        report += "\n"

    if analysis_report['processing_errors']:
        report += "⚠️  Processing Errors:\n"
        for error in analysis_report['processing_errors']:
            report += f"  • {error['filename']}: {error['error']}\n"

    return report

def filter_all_senders(sender_groups: Dict[str, List[Dict]],
                      media_dir: str = "whatsapp_data",
                      strict_mode: bool = False,
                      ultra_conservative: bool = True,
                      output_dir: str = "privacy_filtered_reports") -> Dict[str, Dict]:
    """
    Apply privacy filtering to all senders.

    Args:
        sender_groups (Dict): Dictionary from group_messages_by_sender
        media_dir (str): Directory containing media files
        strict_mode (bool): If True, removes any image with faces detected
        ultra_conservative (bool): If True, uses stricter face detection criteria
        output_dir (str): Directory to save filtering reports

    Returns:
        Dict mapping sender names to their filtering results
    """

    os.makedirs(output_dir, exist_ok=True)
    all_results = {}

    print(f"🔒 Starting privacy filtering for {len(sender_groups)} senders...")
    print(f"📂 Media directory: {media_dir}")
    print(f"🔍 Strict mode: {'ON' if strict_mode else 'OFF'}")
    print("-" * 50)

    for sender_name, messages in sender_groups.items():
        print(f"\n👤 Processing: {sender_name}")

        try:
            safe_messages, filtered_messages, analysis_report = filter_messages_by_privacy(
                messages, media_dir, strict_mode, ultra_conservative
            )

            # Store results
            all_results[sender_name] = {
                'safe_messages': safe_messages,
                'filtered_messages': filtered_messages,
                'analysis_report': analysis_report
            }

            # Create and save privacy report
            privacy_report = create_privacy_report(analysis_report, sender_name)

            # Safe filename for report
            safe_filename = "".join(c for c in sender_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_filename = safe_filename.replace(' ', '_')
            report_path = os.path.join(output_dir, f"{safe_filename}_privacy_report.txt")

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(privacy_report)

            # Print summary
            total_images = analysis_report['image_attachments']
            safe_images = analysis_report['safe_images']
            if total_images > 0:
                safety_rate = (safe_images / total_images) * 100
                print(f"   📊 {safe_images}/{total_images} images safe ({safety_rate:.1f}%)")
            else:
                print(f"   📊 No images to analyze")

        except Exception as e:
            print(f"   ❌ Error processing {sender_name}: {str(e)}")
            all_results[sender_name] = {
                'error': str(e),
                'safe_messages': messages,  # Keep original on error
                'filtered_messages': [],
                'analysis_report': {'error': str(e)}
            }

    print(f"\n✅ Privacy filtering complete!")
    print(f"📁 Reports saved to: {output_dir}")

    return all_results

# Example usage
if __name__ == "__main__":
    from message_date_filter import extract_messages_by_month
    from group_by_sender import group_messages_by_sender

    print("🔒 Privacy-Aware Photo Filtering System")
    print("=" * 50)

    # Extract July 2025 messages
    messages = extract_messages_by_month("whatsapp_data/_chat.txt", month=7, year=2025)
    sender_groups = group_messages_by_sender(messages)

    # Test with one sender first
    if sender_groups:
        test_sender = list(sender_groups.keys())[0]
        test_messages = sender_groups[test_sender]

        print(f"\n🧪 Testing with sender: {test_sender}")
        print(f"📨 Total messages: {len(test_messages)}")

        safe_messages, filtered_messages, report = filter_messages_by_privacy(
            test_messages, "whatsapp_data", strict_mode=False, ultra_conservative=True
        )

        print(f"\n📊 Results:")
        print(f"✅ Safe messages: {len(safe_messages)}")
        print(f"❌ Filtered messages: {len(filtered_messages)}")

        # Show detailed report
        privacy_report = create_privacy_report(report, test_sender)
        print(privacy_report)

        # Ask user if they want to process all senders
        print("\n" + "="*50)
        print("To process all senders, run:")
        print("filter_results = filter_all_senders(sender_groups)")
    else:
        print("❌ No messages found to process")