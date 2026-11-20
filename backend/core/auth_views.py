import logging
from smtplib import SMTPException
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .throttles import LoginRateThrottle, PasswordResetRateThrottle

logger = logging.getLogger("waselni.auth")
User = get_user_model()


class TokenLoginView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        if not settings.DEBUG and not (
            settings.EMAIL_HOST
            and settings.DEFAULT_FROM_EMAIL
            and settings.EMAIL_BACKEND != "django.core.mail.backends.console.EmailBackend"
        ):
            return Response(
                {"detail": "Password recovery is not configured. Contact support."},
                status=503,
            )

        form = PasswordResetForm(data={"email": request.data.get("email", "")})
        if form.is_valid():
            frontend_url = settings.PASSWORD_RESET_FRONTEND_URL
            try:
                form.save(
                    request=request,
                    use_https=urlsplit(frontend_url).scheme == "https",
                    token_generator=default_token_generator,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    email_template_name="core/password_reset_email.txt",
                    subject_template_name="core/password_reset_subject.txt",
                    domain_override=urlsplit(frontend_url).netloc,
                    extra_email_context={"frontend_url": frontend_url},
                )
            except (OSError, SMTPException):
                logger.warning("Password reset email delivery failed.")
        return Response(
            {"detail": "If the account can be recovered, instructions will be sent to its email."},
            status=202,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        uidb64 = str(request.data.get("uid", ""))
        token = str(request.data.get("token", ""))
        new_password = str(request.data.get("new_password", ""))
        confirmation = str(request.data.get("confirm_password", ""))

        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user_id)
                if not default_token_generator.check_token(user, token):
                    return Response({"detail": "This password reset link is invalid or expired."}, status=400)
                form = SetPasswordForm(user, data={
                    "new_password1": new_password,
                    "new_password2": confirmation,
                })
                if not form.is_valid():
                    return Response({
                        field: [str(error) for error in errors]
                        for field, errors in form.errors.items()
                    }, status=400)
                form.save()
                if user.must_change_password:
                    user.must_change_password = False
                    user.save(update_fields=["must_change_password"])
        except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
            return Response({"detail": "This password reset link is invalid or expired."}, status=400)

        return Response({"detail": "Password updated. You can now sign in."})
