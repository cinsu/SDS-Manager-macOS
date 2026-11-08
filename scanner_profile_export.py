# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Conservative lossless validation of offline-editable SDS100 profile settings."""
from profile_schema import diff_sections, patch_fields
from quick_keys_settings import read_quick_keys, patch_quick_keys
from location_settings import read_location_settings, patch_profile
from scanner_profile_records import read_service_types, patch_service_types, read_custom_service_types, patch_custom_service_types


def assess_profile_replacement(original: bytes, proposed: bytes):
    """Authorize only bytes reproducible by the existing offline settings editors."""
    if len(original) > 2_000_000 or len(proposed) > 2_000_000:
        return False, 'profile.cfg exceeds size limit', {}
    try:
        before_keys = read_quick_keys(original)
        after_keys = read_quick_keys(proposed)
        before_location = read_location_settings(original)
        after_location = read_location_settings(proposed)
        # A missing ServiceType row is supported for legacy profiles, but an
        # added or removed row is never authorized.
        before_services = read_service_types(original) if b"ServiceType\t" in original else None
        after_services = read_service_types(proposed) if b"ServiceType\t" in proposed else None
        before_custom = read_custom_service_types(original) if b"CustomServiceType\t" in original else None
        after_custom = read_custom_service_types(proposed) if b"CustomServiceType\t" in proposed else None
        candidate = original
        edits = []
        if before_keys != after_keys:
            candidate = patch_quick_keys(candidate, after_keys)
            edits.append('Favorites quick keys')
        if before_location != after_location:
            candidate = patch_profile(candidate, *after_location)
            edits.append('offline location/GPS settings')
        if before_services != after_services:
            if before_services is None or after_services is None:
                return False, 'ServiceType record cannot be added or removed', {}
            candidate = patch_service_types(candidate, after_services)
            edits.append('service type enablement')
        if before_custom != after_custom:
            if before_custom is None or after_custom is None:
                return False, 'CustomServiceType record cannot be added or removed', {}
            candidate = patch_custom_service_types(candidate, after_custom)
            edits.append('custom/racing service type enablement')
        schema_edits = diff_sections(candidate, proposed)
        if schema_edits:
            candidate = patch_fields(candidate, schema_edits)
            edits.append('validated scanner settings (' + ', '.join(sorted({k for k, _, _ in schema_edits})) + ')')
        if candidate != proposed or not edits:
            return False, 'Changes include unsupported profile fields or byte formatting', {}
        return True, ', '.join(edits), {'field_edits':len(edits),'added':0,'deleted':0}
    except (ValueError, UnicodeError, IndexError, TypeError) as exc:
        return False, 'Invalid or unsupported profile format: ' + str(exc), {}
