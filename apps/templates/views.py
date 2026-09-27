import os
import json
import requests
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.utils import TenantModelViewSetMixin
from apps.templates.models import Template
from apps.templates.serializers import TemplateSerializer


def generate_contextual_fallback_templates(prompt, channel_type, tone, provider):
    """
    Context-aware AI fallback template generator that synthesizes 3 distinct options
    tailored to the prompt, tone, channel (Email / WhatsApp), and provider brand.
    """
    p_lower = prompt.lower()
    provider_name = "ChatGPT (OpenAI)" if provider == 'openai' else "Google Gemini"

    # Keywords classification
    if any(k in p_lower for k in ['discount', 'offer', 'promo', 'sale', 'deal', 'black friday', 'coupon']):
        theme = 'promotion'
    elif any(k in p_lower for k in ['welcome', 'onboarding', 'signup', 'hello', 'join']):
        theme = 'welcome'
    elif any(k in p_lower for k in ['demo', 'meeting', 'call', 'schedule', 'calendar', 'appointment']):
        theme = 'meeting'
    elif any(k in p_lower for k in ['re-engage', 'inactive', 'miss', 'come back', 'winback', 'reengage']):
        theme = 'reengagement'
    else:
        theme = 'outreach'

    if channel_type == 'Email':
        if theme == 'promotion':
            opt1 = {
                'name': f"Special Offer - Warm & Inviting ({tone})",
                'subject': "Exclusive Offer inside for {{first_name}} 🎉",
                'body': f"Hi {{first_name}},\n\nWe wanted to share an exclusive update with you and the team at {{company_name}}!\n\nFor a limited time, enjoy special pricing tailored to accelerate your growth. Simply reply to this email or click below to claim your offer.\n\nBest regards,\nThe Team"
            }
            opt2 = {
                'name': f"Special Offer - High Impact ({tone})",
                'subject': "Limited Time: Special Upgrade for {{company_name}}",
                'body': f"Hello {{first_name}},\n\nDon't miss out! Based on your recent interest, we've unlocked an exclusive promotion for {{company_name}}.\n\nTake advantage of this deal before it expires. Let us know if you'd like us to set this up for you directly!\n\nCheers,\nCustomer Success Team"
            }
            opt3 = {
                'name': f"Special Offer - Direct & Concise ({tone})",
                'subject': "Quick question about your offer, {{first_name}}",
                'body': f"Hey {{first_name}},\n\nQuick heads up: We're running a limited-time promotion that fits perfectly with what {{company_name}} is building.\n\nAre you available for a quick chat this week to review the details?\n\nBest,\nSales Team"
            }
        elif theme == 'welcome':
            opt1 = {
                'name': f"Welcome Series - Warm Intro ({tone})",
                'subject': "Welcome to the family, {{first_name}}! 🚀",
                'body': f"Hi {{first_name}},\n\nWelcome aboard! We're thrilled to have {{company_name}} partnering with us.\n\nHere are a few quick steps to get started immediately. If you have any questions or need setup support, reply directly to this email.\n\nWarmly,\nOnboarding Specialist"
            }
            opt2 = {
                'name': f"Welcome Series - Action Oriented ({tone})",
                'subject': "Your quick start guide for {{company_name}}",
                'body': f"Hello {{first_name}},\n\nReady to get started? We've prepared custom resources to help {{company_name}} launch smoothly.\n\nFeel free to explore our platform features or reply here to book a 1-on-1 walkthrough.\n\nBest regards,\nThe Team"
            }
            opt3 = {
                'name': f"Welcome Series - VIP Touch ({tone})",
                'subject': "A personal welcome for {{first_name}}",
                'body': f"Hey {{first_name}},\n\nJust wanted to personally reach out and welcome you! We're dedicated to helping {{company_name}} achieve great results.\n\nLet us know how we can support you today.\n\nCheers,\nFounder & Team"
            }
        elif theme == 'meeting':
            opt1 = {
                'name': f"Meeting Request - Friendly ({tone})",
                'subject': "Connecting with {{first_name}} from {{company_name}}",
                'body': f"Hi {{first_name}},\n\nHope your week is off to a great start! I'd love to connect briefly to discuss how we can support {{company_name}}'s upcoming goals.\n\nDo you have 15 minutes available later this week?\n\nBest regards,\nOutreach Team"
            }
            opt2 = {
                'name': f"Meeting Request - Value First ({tone})",
                'subject': "Ideas to accelerate growth at {{company_name}}",
                'body': f"Hello {{first_name}},\n\nI noticed {{company_name}} has been expanding recently and put together a few tailored ideas for your team.\n\nWould you be open to a quick 10-minute intro call on Tuesday or Wednesday?\n\nBest,\nGrowth Lead"
            }
            opt3 = {
                'name': f"Meeting Request - Quick Touch ({tone})",
                'subject': "Quick calendar check, {{first_name}}",
                'body': f"Hey {{first_name}},\n\nFollowing up on our recent communications regarding {{company_name}}. Would love to hop on a short call to answer any questions.\n\nLet me know what time works best for you!\n\nThanks,\nSupport Team"
            }
        else:
            opt1 = {
                'name': f"General Outreach - Personal ({tone})",
                'subject': f"Reaching out to {{first_name}} at {{company_name}}",
                'body': f"Hi {{first_name}},\n\n{prompt}\n\nWe'd love to share how we can collaborate with {{company_name}}. Looking forward to hearing your thoughts!\n\nBest regards,\nThe Team"
            }
            opt2 = {
                'name': f"General Outreach - Solution Focus ({tone})",
                'subject': f"Unlocking value for {{company_name}}",
                'body': f"Hello {{first_name}},\n\n{prompt}\n\nOur platform is engineered to streamline outreach and boost engagement for teams like {{company_name}}.\n\nWould love to connect when convenient!\n\nCheers,\nAccount Executive"
            }
            opt3 = {
                'name': f"General Outreach - Direct Touch ({tone})",
                'subject': f"Quick inquiry for {{first_name}}",
                'body': f"Hey {{first_name}},\n\n{prompt}\n\nLet us know if you're open to exploring this for {{company_name}}.\n\nBest,\nClient Relations"
            }
    else:  # WhatsApp
        if theme == 'promotion':
            opt1 = {
                'name': f"WhatsApp Promo - Friendly ({tone})",
                'subject': "",
                'body': f"Hi {{first_name}} 👋! Special offer alert for {{company_name}} 🎉. We're offering an exclusive discount this week. Reply 'YES' to claim your offer now!"
            }
            opt2 = {
                'name': f"WhatsApp Promo - Direct ({tone})",
                'subject': "",
                'body': f"Hey {{first_name}}, don't miss out! Limited time promotion available for {{company_name}}. Tap to chat or reply to this message for instant activation 🚀."
            }
            opt3 = {
                'name': f"WhatsApp Promo - VIP Touch ({tone})",
                'subject': "",
                'body': f"Hello {{first_name}}! Exclusive update for {{company_name}}: Enjoy VIP pricing today only. Let us know if you'd like us to send over the link!"
            }
        elif theme == 'welcome':
            opt1 = {
                'name': f"WhatsApp Welcome - Warm ({tone})",
                'subject': "",
                'body': f"Hi {{first_name}}! Welcome to our platform 🌟. We're excited to support {{company_name}}. Let us know if you need any assistance getting started!"
            }
            opt2 = {
                'name': f"WhatsApp Welcome - Action ({tone})",
                'subject': "",
                'body': f"Hey {{first_name}} 👋, welcome aboard! Ready to kickstart your journey with {{company_name}}? Reply anytime if you have questions!"
            }
            opt3 = {
                'name': f"WhatsApp Welcome - Quick Check ({tone})",
                'subject': "",
                'body': f"Hello {{first_name}}, thanks for joining us! We've set up everything for {{company_name}}. Have a great day ahead!"
            }
        else:
            opt1 = {
                'name': f"WhatsApp Message - Conversational ({tone})",
                'subject': "",
                'body': f"Hi {{first_name}} 👋! {prompt}. Hope all is well at {{company_name}}! Let's connect soon."
            }
            opt2 = {
                'name': f"WhatsApp Message - Quick Note ({tone})",
                'subject': "",
                'body': f"Hey {{first_name}}, quick message regarding {{company_name}}: {prompt}. Reply when you get a chance!"
            }
            opt3 = {
                'name': f"WhatsApp Message - Direct ({tone})",
                'subject': "",
                'body': f"Hello {{first_name}}! Reaching out from our team: {prompt}. Looking forward to your response!"
            }

    return [opt1, opt2, opt3]


class TemplateViewSet(TenantModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer

    @action(detail=False, methods=['post'], url_path='generate_ai')
    def generate_ai(self, request):
        prompt = request.data.get('prompt', '').strip()
        channel_type = request.data.get('type', 'Email')  # Email or WhatsApp
        provider = request.data.get('provider', 'openai')  # openai or gemini
        tone = request.data.get('tone', 'Professional')
        count = int(request.data.get('count', 3))

        if not prompt:
            return Response({'detail': 'prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)

        openai_key = os.environ.get('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
        gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None)

        generated_options = []

        if provider == 'openai' and openai_key:
            try:
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                system_instruction = (
                    f"You are an expert copywriter. Generate {count} distinct message templates for channel: {channel_type}. "
                    f"Tone: {tone}. Use placeholders like {{first_name}}, {{company_name}}, {{phone}}, {{email}} where appropriate. "
                    f"Return a valid JSON object containing key 'options' which is an array of {count} objects, each with 'name', 'subject' (string, empty if WhatsApp), and 'body'."
                )
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7
                }
                res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=12)
                if res.status_code == 200:
                    content_str = res.json()['choices'][0]['message']['content']
                    clean_str = content_str.replace('```json', '').replace('```', '').strip()
                    parsed = json.loads(clean_str)
                    if isinstance(parsed, list):
                        generated_options = parsed
                    elif isinstance(parsed, dict) and 'options' in parsed:
                        generated_options = parsed['options']
                    elif isinstance(parsed, dict) and 'templates' in parsed:
                        generated_options = parsed['templates']
            except Exception as e:
                print(f"[OpenAI Generation Error] {e}")

        elif provider == 'gemini' and gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                system_instruction = (
                    f"You are an expert copywriter. Generate {count} distinct message templates for channel: {channel_type}. "
                    f"Tone: {tone}. Use placeholders like {{first_name}}, {{company_name}}, {{phone}}, {{email}} where appropriate. "
                    f"Return ONLY a valid JSON array of objects with keys: 'name', 'subject', 'body'."
                )
                payload = {
                    "contents": [{
                        "parts": [{"text": f"{system_instruction}\nPrompt: {prompt}"}]
                    }]
                }
                res = requests.post(url, json=payload, timeout=12)
                if res.status_code == 200:
                    raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                    clean_json = raw_text.replace('```json', '').replace('```', '').strip()
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, list):
                        generated_options = parsed
                    elif isinstance(parsed, dict) and 'options' in parsed:
                        generated_options = parsed['options']
            except Exception as e:
                print(f"[Gemini Generation Error] {e}")

        # Fallback generator if keys are absent or API call returns empty
        if not generated_options:
            generated_options = generate_contextual_fallback_templates(prompt, channel_type, tone, provider)

        return Response({
            'prompt': prompt,
            'type': channel_type,
            'provider': provider,
            'tone': tone,
            'options': generated_options
        }, status=status.HTTP_200_OK)
