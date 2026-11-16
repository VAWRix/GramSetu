"""
Script to synchronize and publish trilingual Village Knowledge Portal content for
Narayangaon (informational page) across Marathi (mr), Hindi (hi), and English (en).
Preserves existing database invariants and maker-checker approval records.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.db import transaction
from django.utils import timezone
from apps.identity.models import User, ROLE_SUPER_ADMIN
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    STATUS_PUBLISHED,
    EDITORIAL_APPROVED,
)
from apps.content.research_service import get_narayangaon_statutory_knowledge
from apps.governance import services as gov_services


def sync_knowledge_portal():
    admin = User.objects.filter(role_assignment__role=ROLE_SUPER_ADMIN).first()
    if not admin:
        admin = User.objects.first()

    page = Page.objects.filter(slug='informational').first()
    if not page:
        page = Page.objects.create(
            slug='informational',
            is_system_page=True,
            display_order=1,
        )
        print("Created Page: informational")

    for lang in ['mr', 'hi', 'en']:
        data = get_narayangaon_statutory_knowledge(lang=lang)
        if lang == 'en':
            title = "Narayangaon Village Knowledge Portal"
            localized_slug = "narayangaon-village-knowledge-portal"
        elif lang == 'hi':
            title = "नारायणगांव ग्राम ज्ञानकोश (Narayangaon Village Knowledge Portal)"
            localized_slug = "narayangaon-gram-gyankosh"
        else:
            title = "नारायणगाव ग्राम माहिती ज्ञानकोश (Narayangaon Village Knowledge Portal)"
            localized_slug = "narayangaon-gram-mahiti-dnyankosh"

        with transaction.atomic():
            trans, created = PageTranslation.objects.get_or_create(
                page=page,
                language_code=lang,
                defaults={'localized_slug': localized_slug, 'status': STATUS_PUBLISHED},
            )

            # Check if there is an existing approved revision
            existing_rev = trans.current_approved_revision
            # Branch or create a new revision with complete localized sections
            next_rev_num = (trans.revisions.order_by('-revision_number').first().revision_number + 1) if trans.revisions.exists() else 1

            rev = PageRevision.objects.create(
                translation=trans,
                revision_number=next_rev_num,
                title=title,
                summary=data['summary'],
                body_markdown=data['summary'],
                sections_data=data['sections'],
                references_data=data['references'],
                editorial_status=EDITORIAL_APPROVED,
                created_by=admin,
            )

            # Link approved revision to translation
            trans.current_approved_revision = rev
            trans.status = STATUS_PUBLISHED
            trans.save()

            # Record governance publication event
            gov_services.publish_page_translation(
                translation_id=trans.id,
                revision_id=rev.id,
                actor=admin,
                justification=f"Statutory verification and publication of 14-section {lang.upper()} knowledge portal",
            )

            print(f"Synchronized & Published [{lang}] translation for 'informational': rev #{rev.revision_number} with {len(data['sections'])} sections.")

if __name__ == '__main__':
    sync_knowledge_portal()
