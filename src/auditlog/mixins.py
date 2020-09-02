import json

from django.conf import settings
try:
    from django.core import urlresolvers
except ImportError:
    from django import urls as urlresolvers
try:
    from django.urls.exceptions import NoReverseMatch
except ImportError:
    from django.core.urlresolvers import NoReverseMatch
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import LogEntry
from .registry import auditlog

MAX = 75


class LogEntryAdminMixin(object):

    def created(self, obj):
        return obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    created.short_description = 'Created'

    def user_url(self, obj):
        if obj.actor:
            app_label, model = settings.AUTH_USER_MODEL.split('.')
            viewname = 'admin:%s_%s_change' % (app_label, model.lower())
            try:
                link = urlresolvers.reverse(viewname, args=[obj.actor.id])
            except NoReverseMatch:
                return u'%s' % (obj.actor)
            return format_html(u'<a href="{}">{}</a>', link, obj.actor)

        return 'system'
    user_url.short_description = 'User'

    def resource_url(self, obj):
        app_label, model = obj.content_type.app_label, obj.content_type.model
        viewname = 'admin:%s_%s_change' % (app_label, model)
        try:
            args = [obj.object_pk] if obj.object_id is None else [obj.object_id]
            link = urlresolvers.reverse(viewname, args=args)
        except NoReverseMatch:
            return obj.object_repr
        else:
            return format_html(u'<a href="{}">{}</a>', link, obj.object_repr)
    resource_url.short_description = 'Resource'

    def msg_short(self, obj):
        if obj.action in [LogEntry.Action.DELETE, LogEntry.Action.VIEW]:
            return ''
        changes = json.loads(obj.changes)
        s = '' if len(changes) == 1 else 's'
        fields = ', '.join(changes.keys())
        if len(fields) > MAX:
            i = fields.rfind(' ', 0, MAX)
            fields = fields[:i] + ' ..'
        return '%d change%s: %s' % (len(changes), s, fields)
    msg_short.short_description = 'Changes'

    def msg(self, obj):
        if obj.action in [LogEntry.Action.DELETE, LogEntry.Action.VIEW]:
            return ''
        changes = json.loads(obj.changes)
        msg = '<table><tr><th>#</th><th>Field</th><th>From</th><th>To</th></tr>'
        for i, field in enumerate(sorted(changes), 1):
            value = [i, field] + (['***', '***'] if field == 'password' else changes[field])
            msg += format_html('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>', *value)

        msg += '</table>'
        return mark_safe(msg)
    msg.short_description = 'Changes'


class ViewedViewSetMixin:
    """
    Mixin for Django Rest Framework ViewSets that will create a log entry when someone views an instance of a Model
    """

    def retrieve(self, request, *args, **kwargs):
        # Get the object being retrieved and check that it has been registered with the registry
        obj = self.get_object()

        if auditlog.contains(obj):
            # Get the current authenticated user and their IP address
            user = request.user if request.user and request.user.is_authenticated else None
            remote_addr = request.META.get('REMOTE_ADDR')

            # In case of proxy, set 'original' address
            if request.META.get('HTTP_X_FORWARDED_FOR'):
                remote_addr = request.META.get('HTTP_X_FORWARDED_FOR').split(',')[0]

            # Force the creation of a new LogEntry
            LogEntry.objects.force_log_create(
                obj,
                action=LogEntry.Action.VIEW,
                actor=user,
                remote_addr=remote_addr
            )

        return super().retrieve(request, *args, **kwargs)


class ViewedDetailViewMixin:
    """
    Mixin for Django DetailViews that will create a log entry when someone requests this DetailView
    """

    def dispatch(self, request, *args, **kwargs):
        if auditlog.contains(self.model):
            # Get the current authenticated user and their IP address
            user = request.user if request.user and request.user.is_authenticated else None
            remote_addr = request.META.get('REMOTE_ADDR')

            # In case of proxy, set 'original' address
            if request.META.get('HTTP_X_FORWARDED_FOR'):
                remote_addr = request.META.get('HTTP_X_FORWARDED_FOR').split(',')[0]

            # Force the creation of a new LogEntry
            LogEntry.objects.force_log_create(
                self.get_object(),
                action=LogEntry.Action.VIEW,
                actor=user,
                remote_addr=remote_addr
            )

        return super.dispatch(request, *args, **kwargs)
