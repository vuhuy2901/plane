# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

class DisableCSRFMiddleware:
    """
    Middleware that disables CSRF verification for all requests in development.
    Sets request._dont_enforce_csrf_checks = True which is honored by
    Django's CsrfViewMiddleware and DRF's SessionAuthentication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        setattr(request, "_dont_enforce_csrf_checks", True)
        return self.get_response(request)
