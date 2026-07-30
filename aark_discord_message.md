# Aark Integration Follow-up

Thanks for the updated integration guide. We tested the documented self-serve
flow against the live API today and isolated two compatibility issues:

1. A visible `app.aark.digital` session with the exact documented EIP-191 open
   signature returns `code: 400, Invalid Signature`.
2. A visible `https://tick-project.vercel.app` session obtains a fresh
   production `TRADE` token, but the same order with Aark's current live
   EIP-712 `MoonOrder` signature returns error `9999`.

As a positive control, we submitted the EIP-712 `MoonOrder` with a visible
`app.aark.digital` token. It returned `code: 200`; the BTC 500x position opened,
closed successfully, reconciled, and was fully withdrawn. This matches the
current production bundle (`v3.4.26`), which uses EIP-712 `MoonOrder` and
`MoonCloseOrder`.

Could you confirm:

- whether EIP-712 is the canonical signing format for new integrations;
- whether `tick-project.vercel.app` needs to be added to the production
  reCAPTCHA configuration, or whether you prefer partner authentication; and
- the staging reCAPTCHA site key mentioned in the guide?

Our website is https://tick-project.vercel.app. We can provide the exact test
wallet, timestamps, and request fields privately if useful.
