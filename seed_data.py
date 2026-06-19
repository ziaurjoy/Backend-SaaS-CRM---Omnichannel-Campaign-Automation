import os
import django

# Set settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.tenants.models import Business, BusinessMember
from apps.crm.models import Lead, Tag, LeadActivity
from apps.templates.models import Template
from apps.campaigns.models import Campaign

User = get_user_model()

def seed():
    print("Seeding database...")
    
    # 1. Create Demo User
    user, created = User.objects.get_or_create(
        username="demo",
        defaults={
            "email": "demo@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+1234567890",
            "timezone": "UTC"
        }
    )
    if created:
        user.set_password("password123")
        user.save()
        print("Demo user created.")
    else:
        print("Demo user already exists.")

    # 2. Create Business Workspace
    business, b_created = Business.objects.get_or_create(
        name="Acme Corporation",
        defaults={
            "industry": "Software",
            "website": "https://acme.com",
            "country": "United States",
            "address": "123 Innovation Way, Tech City",
            "timezone": "UTC"
        }
    )
    if b_created:
        print("Acme Corporation business created.")
    else:
        print("Acme Corporation business already exists.")

    # 3. Create Business Member Owner
    member, m_created = BusinessMember.objects.get_or_create(
        business=business,
        user=user,
        defaults={"role": "Owner"}
    )
    if m_created:
        print("Membership created as Owner.")

    # 4. Create Tags
    tag_vip, _ = Tag.objects.get_or_create(business=business, name="VIP")
    tag_cold, _ = Tag.objects.get_or_create(business=business, name="Cold Outreach")
    tag_warm, _ = Tag.objects.get_or_create(business=business, name="Warm Lead")

    # 5. Create Leads
    leads_data = [
        {"name": "Alice Johnson", "email": "alice@gmail.com", "phone": "+1 555-0100", "stage": "New", "source": "Manual"},
        {"name": "Bob Smith", "email": "bob@acme.com", "phone": "+1 555-0101", "stage": "Contacted", "source": "Google Places"},
        {"name": "Charlie Brown", "email": "charlie@warm.com", "phone": "+1 555-0102", "stage": "Qualified", "source": "Manual"},
        {"name": "Diana Prince", "email": "diana@amazon.com", "phone": "+1 555-0103", "stage": "Proposal", "source": "Google Places"},
        {"name": "Evan Wright", "email": "evan@woncorp.com", "phone": "+1 555-0104", "stage": "Won", "source": "Manual"}
    ]

    for lead_item in leads_data:
        lead, l_created = Lead.objects.get_or_create(
            business=business,
            name=lead_item["name"],
            defaults={
                "email": lead_item["email"],
                "phone": lead_item["phone"],
                "stage": lead_item["stage"],
                "source": lead_item["source"],
                "status": "Lead"
            }
        )
        if l_created:
            # Add appropriate tags and logs
            if lead_item["stage"] == "Qualified" or lead_item["stage"] == "Won":
                lead.tags.add(tag_warm, tag_vip)
            else:
                lead.tags.add(tag_cold)
                
            LeadActivity.objects.create(
                lead=lead,
                activity_type="Log",
                description="Lead added via seed script."
            )
            print(f"Created lead: {lead.name}")

    # 6. Create Email Template
    template, t_created = Template.objects.get_or_create(
        business=business,
        name="Welcome Outreach",
        defaults={
            "type": "Email",
            "subject": "Hi {{first_name}}, let's connect!",
            "body": "Hello {{first_name}},\n\nI saw your business {{company_name}} and would love to connect to see if we can help you automate your outreach campaigns.\n\nBest regards,\nJohn Doe"
        }
    )
    if t_created:
        print("Welcome template created.")

    # 7. Create Campaign
    campaign, c_created = Campaign.objects.get_or_create(
        business=business,
        name="Summer Outreach Campaign 2026",
        defaults={
            "template": template,
            "channel": "Email",
            "status": "Draft",
            "schedule_type": "Immediate"
        }
    )
    if c_created:
        print("Outreach Campaign created.")

    print("Seeding complete successfully!")

if __name__ == "__main__":
    seed()
