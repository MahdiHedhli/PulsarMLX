# Private status notifications

Notification destinations are operator configuration, not repository constants.
Set `PULSAR_NTFY_URL` privately to the approved HTTPS endpoint and topic before
calling `scripts/research/notify_status.sh`. The helper has no fallback topic and
refuses missing configuration or non-HTTPS destinations. Do not commit the value,
credentials, local configuration, or receipt bodies that reveal the destination.

Topic privacy and authorization must be enforced by the notification service.
A renamed or unguessable topic is not authentication. This helper does not create
access controls, rotate topics, or change any running client's configuration.
Use a protected endpoint and its approved authentication mechanism where needed.

A notification response acknowledges publication only. It is not an operator GO,
reviewer verdict, proof of human acknowledgement, or permission to resume a job.
Existing execution approvals and all qualification gates remain separate.

Public historical notes use `<private-notification-topic>` in place of an
operator-specific destination. This privacy redaction changes neither recorded
outcomes nor the historical source revisions. Old Git revisions, other branches,
tags, pull-request diffs, cached views, forks and existing clones are not erased
by a forward cleanup commit. Retire an exposed destination before treating a new
notification channel as private.
