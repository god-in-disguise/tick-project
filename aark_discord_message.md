# Aark Integration Follow-up

Thanks for the updated integration guide. It answered the broad access question:
we can use the self-serve REST/WebSocket flow, per-user delegate signatures,
and a fresh browser `TRADE` token from the TICK PWA. We have confirmed the
published production site key issues a token from
`https://tick-project.vercel.app`.

We have one implementation detail to confirm before the next funded canary. The
guide currently documents EIP-191 signatures for Moon open and close, while the
current `app.aark.digital` production bundle (`v3.4.26`) uses EIP-712
`MoonOrder` and `MoonCloseOrder`. Our successful live canary also used the
EIP-712 format.

Which signing format should a new integration treat as canonical going forward?
Could you also share the staging reCAPTCHA site key mentioned in the guide?

We do not need partner authentication for the first browser-based integration.
If we later move opens fully server-side, we will send a partner signing address
for registration separately.
