# A CLI tool to automate AWS SSO login. It uses selenium with chrome under the hood.

### 1. Install with `pipx`

```
pipx install auto-aws-sso
```

### 2. Run first time with `--no-headless`

You need that to save your browser user data. Browser will be opened by `auto-aws-sso`.

```
auto-aws-sso --no-headless
```

## How it works

Script reads `aws sso login` output from stdin and parses it. Then it opens chrome with user data dir and navigates to AWS SSO login page. After that it fills the form and submits it. Finally it waits for aws sso to confirm login and then it closes chrome. There is default headless mode so you won't see anything. If you want to see what's going on you can use `--no-headless` option. It will open chrome and you will see what's going on.

## Prerequisites

You need `google-chrome` installed and in your `PATH`.
