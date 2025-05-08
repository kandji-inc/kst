# Kandji Sync Toolkit

`kst` (*pronounced kast*) is a utility for managing resources via the Kandji API.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
  - [Using Homebrew](#using-homebrew)
  - [Using uv](#using-uv)
  - [Using pipx](#using-pipx)
- [Quick Start](#quick-start)
- [Getting Help](#getting-help)
- [Creating Your Local Repository](#creating-your-local-repository)
- [Authenticate with Your Kandji Tenant](#authenticate-with-your-kandji-tenant)
- [Populating Your Local Repository](#populating-your-local-repository)
  - [Fetching Existing Resources](#fetching-existing-resources)
  - [Create a New Resource](#create-a-new-resource)
  - [Import a Existing Local Script or Profile](#import-a-existing-local-script-or-profile)
- [Edit a Local Resource](#edit-a-local-resource)
- [Making a Custom Script Available in Self Service](#making-a-custom-script-available-in-self-service)
  - [Using the --self-service option](#using-the---self-service-option)
  - [Using the --self-service and --category options](#using-the---self-service-and---category-options)
- [Pushing Changes to Kandji](#pushing-changes-to-kandji)
- [Syncing Changes with Kandji](#syncing-changes-with-kandji)
- [List Resource Sync Statuses](#list-resource-sync-statuses)
- [Show Resource Details](#show-resource-details)
- [Local Resource Directory Structure](#local-resource-directory-structure)
  - [Custom Profile](#custom-profile)
  - [Custom Script](#custom-script)
- [Manually Creating Resources](#manually-creating-resources)

## Features

- Create and sync a local repository of custom profiles or scripts with your Kandji tenant
- Import existing profiles and scripts without copy/pasting
- List or show details of local and remote resources directly from the command line
- Format output as structured YAML, plist, or JSON for use with other tools
- Build your own integration for managing custom profiles or scripts with a fully featured Python client module

## Installation

### Using Homebrew

>[!TIP]
> `brew` the missing (yet ubiquitous) macOS package manager for CLI tools and
> native macOS applications.
>
> More information at [brew.sh](https://docs.astral.sh/uv/getting-started/installation/).

```sh
brew tap kandji-inc/kst https://github.com/kandji-inc/kst.git
brew install kst
```

### Using uv

>[!TIP]
> `uv` is a single binary solution for managing Python environments with a wide
> range of features.
>
> More information at [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv tool install kst
```

### Using pipx

>[!TIP]
> `pipx` is a 100% Python solution to install and run Python tools in isolated
> environments.
>
> More information at [pipx.pypa.io](https://pipx.pypa.io/stable/).

```sh
pipx install kst
```

## Quick Start

Follow the steps below to quickly get up and running with a local copy of your Kandji Custom Resources.

1. Create a new local repository: `kst new my-repo`
2. Change directories: `cd my-repo`
3. Set your credentials:
    1. `export KST_TENANT=<YOUR_API_URL_HERE>`
    2. `export KST_TOKEN=<YOUR_API_TOKEN_HERE>`
4. Download your custom profiles from Kandji: `kst profile pull --all`
5. Download your custom scripts from Kandji `kst script pull --all`

> [!Note]
> Replace `<YOUR_API_URL_HERE>` and `<YOUR_API_TOKEN_HERE>` with your API URL and token. See the authentication section
> [below](#authenticate-with-your-kandji-tenant) for more details.

## Getting Help

Each command and subcommand has its own help screen, which can be accessed by appending `--help`. For example,
`kst --help` will display usage information, available options, a list of root-level commands, and a short description
of each command (see below). Help screens for each subcommand can be accessed in the same way (e.g., `kst new --help`).

```
Usage: kst [OPTIONS] COMMAND [ARGS]...

 Kandji Sync Toolkit, a utility for local management of Kandji resources.

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --version                     Show the version.                                                                      │
│ --install-completion          Install completion for the current shell.                                              │
│ --show-completion             Show completion for the current shell, to copy it or customize the installation.       │
│ --help                        Show this message and exit.                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Logging ────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --log-path        PATH  Path to the log file.                                                                        │
│ --debug                 Enable debug logging.                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ profile   Interact with Kandji Custom Profiles                                                                       │
│ script    Interact with Kandji Custom Scripts                                                                        │
│ new       Create a new kst repository                                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Creating Your Local Repository

Before doing anything else, you'll need to create a local repository. A `kst` repository can be created in any directory
using `kst new`. Under the hood, a `kst` repository just a `git` repository with a `.kst` file at its root, but using
the command will include a handy `README.md` to get you started.

```
❯ kst new kst-repo
Created a new kst repository at kst-repo
Check out the included README.md file for more information on getting started.
```

## Authenticate with Your Kandji Tenant

With no configuration, you will be prompted for a Kandji tenant API URL and a token when running a command that
requires it.

```
$ kst profile sync --all
Enter Kandji Tenant URL: https://mysubdomain.api.kandji.io
Enter API Token: ************
```

However, it's generally a better idea to store the credentials in environment variables. This removes the need to enter
credentials for every command. The following environment variables are automatically checked by `kst` before prompting
the user.

- `KST_TENANT`: The `https` API URL of your Kandji tenant (e.g., https://mysubdomain.api.kandji.io).
- `KST_TOKEN`: The API token with permissions to your Kandji tenant (see documentation:
  [Generate an API Token](https://support.kandji.io/kb/kandji-api#generate-an-api-token)).

>[!TIP]
> These values can be added to your shell's startup file to be exported automatically.
>
> Example `~/.profile`, `~/.zshrc`, or `~/.bashrc`
>
> ```sh
> export KST_TENANT="https://mysubdomain.api.kandji.io"
> export KST_TOKEN="not-a-real-token"
> ```

## Populating Your Local Repository

### Fetching Existing Resources

If you already have resources in Kandji, you can have `kst` pull all or some of them down to your local repository with
a single command. Use the `--all` option to pull all of a resource type into the local repo or select specific resources
with the `--id` option. `--id` can be specified more than one to include multiple resources.

* `kst profile pull [OPTIONS]`
* `kst script pull [OPTIONS]`

This will create a `profiles` or `scripts` directory in your repository, if one doesn't exist, and download each Kandji
resource and its metadata into a subdirectory.

The `pull` command can also be used to update existing resources with changes from your Kandji tenant or to delete
resources that no longer exist. By default, nothing is deleted and only resources without local updates are pulled. This
behavior can be modified by passing `--force` (to overwrite local changes) or `--clean` (to delete local resources which
are not present in Kandji).

> [!NOTE]
> The `--clean` option can only be used with `--all`. If you would like to delete only specific resources use the
> `delete` command described below.

If you would like to see what would happen (without making any changes), you can use the `--dry-run` flag. This will
print a full list of actions which would have occurred.

### Create a New Resource

The simplest means of creating a new local script or profile is using the `new` command.

* `kst profile new [OPTIONS]`
* `kst script new [OPTIONS]`

Without any options, this will create a new resource in the respective directory and populate it with default metadata
and content. The defaults match Kandji's defaults for creating a new script or profile in the user interface (where
possible). It's generally recommended to at least specify a name (via the `--name` option) since the resource directory
is named accordingly. Other options can be included to modify the default settings. For a full list of options, see the
`--help` message for each new command.

> [!TIP]
> You can rename or move a resource's directory anywhere within the main profiles/scripts subdirectories you see fit
> without affecting the resource. The resources's name is determined by the `name` key in the info file.

#### Examples:
```
kst profile new --name "My Profile" --runs-on mac --active
```

```
kst script new --name "My Script" --execution-frequency every_15_min --include-remediation
```

### Import a Existing Local Script or Profile

If you already have a mobileconfig or a script you want to deploy in Kandji, you can import the content
into a new resource instead of creating one from scratch. For profiles, use the `--import` option to specify the path to
the mobileconfig file. For scripts, use the `--import-audit` or `--import-remediation` options. These options can be
used with other `new` command options to specify additional metadata.

#### Examples:
```
kst profile new --import /path/to/MyProfile.mobileconfig
```

```
kst script new --name "My Script" --import-audit /path/to/audit.sh --import-remediation /path/to/remediation.sh
```

## Edit a Local Resource

Editing a script or profile can be done in the text editor of your choice. Simply open the file, make your desired
modifications, and save the file. Any changes will be recognized the next time `kst` is run. This includes moving a
resource directory, renaming, etc.

> [!IMPORTANT]
> *Do not edit the `id` and `sync_hash` keys.*
> If an `id` changes then the resource will be disconnected from its Kandji tenant counterpart and identified as a new
> resource. The `sync_hash` is used to automatically identify remote vs local changes to a resource. If it is missing
> or invalid, the resource will show "Conflicting Changes" and  a forced push/pull will be required.

## Making a Custom Script Available in Self Service

You can use the `kst script new --self-service` option to make a custom script Library Item available via Kandji
Self Service. By default, if the `--category` option is not also provided, `kst` will attempt to add the script to
the `Utilities` category. The `Utilities` category is present by default on all Kandji tenants. If the `Utilities`
category was deleted or renamed, an error will be raised and you will need to provide a category.

>[!TIP]
> To see or add additional Self Service categories, head to your Kandji tenant and go to `Settings > Self Service`.
>
> More info - [Self Service Settings KB](https://support.kandji.io/kb/self-service-settings)
>

### Using the --self-service option

```shell
kst script new --name ss_script_no_category --self-service
```

The above command tells `kst` to create a new custom script Library Item called _ss_script_no_category_ and make that
custom script available in Self Service under the `Utilities` category.

If we take a look at the associated info file, we see that `show_in_self_service` is set to `true` and the
`self_service_category` is set to `Utilities`.

```xml
<dict>
    <key>active</key>
    <false/>
    <key>execution_frequency</key>
    <string>once</string>
    <key>id</key>
    <string>2b95fd99-06ec-4492-a934-e44ab8e113e9</string>
    <key>name</key>
    <string>ss_script_option</string>
    <key>restart</key>
    <false/>
    <key>self_service_category_id</key>
    <string>Utilities</string>
    <key>self_service_recommended</key>
    <false/>
    <key>show_in_self_service</key>
    <true/>
</dict>
```

### Using the --self-service and --category options

```shell
kst script new --name ss_script_option --self-service --category Apps
```

The above command tells KST to create a new custom script Library Item called _ss_script_option_ and make that custom
script available in Self Service under the `Apps` category.

Looking at the associated info file, we see that `show_in_self_service` is set to `true` and the
`self_service_category` is set to `Apps`.

```xml
<dict>
    <key>active</key>
    <false/>
    <key>execution_frequency</key>
    <string>once</string>
    <key>id</key>
    <string>2b95fd99-06ec-4492-a934-e44ab8e113e9</string>
    <key>name</key>
    <string>ss_script_option</string>
    <key>restart</key>
    <false/>
    <key>self_service_category_id</key>
    <string>Apps</string>
    <key>self_service_recommended</key>
    <false/>
    <key>show_in_self_service</key>
    <true/>
</dict>
```

Check out `kst script new --help` for additional usage details.

## Pushing Changes to Kandji

Use the `push` command to upload new or updated resources to your Kandji tenant.

* `kst profile push [OPTIONS]`
* `kst script push [OPTIONS]`

You can choose which resources to push using the `--all`, `--id`, and `--path` options. `--id` and `--path` can be
specified more than once to include more than one resource.

By default, only new local resources and resources with only local updates will be pushed. Nothing will be deleted or
overwritten. In order to overwrite changes in the Kandji tenant, use the `--force` option. To delete resources in Kandji
which are not present in the local repository, use the `--clean` option.

> [!NOTE]
> The `--clean` option can only be used with `--all`. If you would like to delete only specific resources use the
> `delete` command described below.

#### Examples:
```
kst profile push --id "de6cf090-cf14-4517-bc8e-110f2e4ed56a"
```

```
kst script push --all --clean
```

## Syncing Changes with Kandji

The `sync` command can be used to push and pull changes simultaneously.

* `kst profile sync [OPTIONS]`
* `kst script sync [OPTIONS]`

In order to make updates more seamless, the `sync` command will create missing resources in both the local repository
and the Kandji tenant as well as updating either with changes. In cases where update direction cannot be definitively
determined, a conflicting change is shown and the resource is skipped.

The `sync` command includes similar options to the `push` and `pull` commands with the addition of `--force-mode` to
to resolve conflicts. the `--force-mode` option can be set to `push` or `pull` in order to automatically overwrite
conflicting changes when they arise.

#### Examples:
```
kst profile sync --id "18f75e5f-5a79-45ef-a354-314c517b9280"
```

```
kst profile sync --all --force-mode push
```

## List Resource Sync Statuses

The `list` commands makes it simple to print a quick view of all your profiles or scripts as well as their sync status.

* `kst profile list [OPTIONS]`
* `kst script list [OPTIONS]`

If you would like to limit the list to remote or local resources only you can pass the `--local` or `--remote` flags
respectively. Similarly, if you want to to only show resources with a specific status you can use the `--include` or
`--exclude` flags. Include and exclude can be used multiple times to specify more than one status. Available statuses
include: no_changes, new_remote, updated_remote, new_local, updated_local, conflict

The list output format can also be modified. By default, a simple human readable table is shown. However, if you
prefer more structured output, use the `--format` option to choose `plist`, `json`, or `yaml`. This can be especially
useful when piping `kst` output to other command line tools.

## Show Resource Details

Use the `show` command to display the full metadata and content of a custom resource.

* `kst profile show [OPTIONS] PROFILE`
* `kst script show [OPTIONS] SCRIPT`

The first argument should be the ID or path of a profile or script.

By default, the local resource is shown in a human readable table format. This can be modified by passing the `--remote`
flag to show the Kandji tenant's version. The `--format` option can be passed with `plist`, `json`, or `yaml` to display
the content and metadata in a specific structured format.

Additionally, for profiles you can pass the `--profile` flag to show only the profile mobileconfig content. For scripts,
you can pass `--audit` or `--remediation` to show their respective content.

#### Example Profile Output
```
$ kst profile show a5f20d99-315e-40b5-a3d5-7cd96f5f2ae4

Custom Profile Details (Local)
┌────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ID             │ a5f20d99-315e-40b5-a3d5-7cd96f5f2ae4                                                                │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Name           │ New Profile                                                                                         │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ MDM Identifier │ com.kandji.profile.custom.a5f20d99-315e-40b5-a3d5-7cd96f5f2ae4                                      │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Active         │ False                                                                                               │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Runs On        │ Mac, iPhone, iPad, TV, and Vision                                                                   │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Created At     │ 2025-04-22T14:48:36.481752Z                                                                         │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Updated At     │ 2025-04-22T14:48:36.481768Z                                                                         │
├────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Profile        │ <?xml version="1.0" encoding="UTF-8"?>                                                              │
│                │ <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.d… │
│                │ <plist version="1.0">                                                                               │
│                │ <dict>                                                                                              │
│                │     <key>PayloadContent</key>                                                                       │
│                │     <array>                                                                                         │
│                │         <dict/>                                                                                     │
│                │     </array>                                                                                        │
│                │     <key>PayloadDisplayName</key>                                                                   │
│                │     <string>New Profile</string>                                                                    │
│                │     <key>PayloadIdentifier</key>                                                                    │
│                │     <string>com.kandji.profile.custom.a5f20d99-315e-40b5-a3d5-7cd96f5f2ae4</string>                 │
│                │     <key>PayloadScope</key>                                                                         │
│                │     <string>System</string>                                                                         │
│                │     <key>PayloadType</key>                                                                          │
│                │     <string>Configuration</string>                                                                  │
│                │     <key>PayloadUUID</key>                                                                          │
│                │     <string>e6291f0f-f825-51b8-9c95-faad71e73540</string>                                           │
│                │     <key>PayloadVersion</key>                                                                       │
│                │     <integer>1</integer>                                                                            │
│                │ </dict>                                                                                             │
│                │ </plist>                                                                                            │
│                │                                                                                                     │
└────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Example Script Output
```
$ kst script show cb3260ce-006a-4985-b06e-d7ea52c09151

Custom Script Details (Local)
┌──────────────────────────┬────────────────────────────────────────────────────────┐
│ ID                       │ cb3260ce-006a-4985-b06e-d7ea52c09151                   │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Name                     │ New Script                                             │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Active                   │ False                                                  │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Execution Frequency      │ Once                                                   │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Restart                  │ False                                                  │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Show in Self Service     │ False                                                  │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Self Service Category ID │                                                        │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Self Service Recommended │                                                        │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Created At               │ 2025-04-23T15:00:47.370018Z                            │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Updated At               │ 2025-04-23T15:00:47.370018Z                            │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Audit Script             │ #!/bin/zsh -f                                          │
│                          │ # https://support.kandji.io/kb/custom-scripts-overview │
│                          │                                                        │
│                          │ echo "Hello, World!"                                   │
│                          │ exit 0                                                 │
│                          │                                                        │
├──────────────────────────┼────────────────────────────────────────────────────────┤
│ Remediation Script       │                                                        │
└──────────────────────────┴────────────────────────────────────────────────────────┘
```

## Local Resource Directory Structure

Since Kandji resources must also contain metadata (e.g. `active` or `name`), each resources's on disk representation is
actually a directory of associated files. Certain files are required for a directory to be recognized as a resource.

>[!TIP]
> Additional files, such as a `README.md`, can be added without causing issues so long as they cannot be confused with
> the required files.

### Custom Profile

Each profile requires:
1. A directory within a kst repository `profiles` directory containing the profile's files
2. Exactly one `info.[plist|yaml|json]` file containing the profile's associated metadata
3. Exactly one `.mobileconfig` file containing the profile's content

```
$ lsd --tree profiles/MyFancyProfile
 MyFancyProfile
├──  info.yaml
└──  profile.mobileconfig
```

`info.yaml`
```yaml
id: 54bef6b3-b25e-44b4-89fd-d528d73939e4
name: MyFancyProfile
active: false
mdm_identifier: com.kandji.profile.custom.54bef6b3-b25e-44b4-89fd-d528d73939e4
runs_on_mac: true
runs_on_iphone: true
runs_on_ipad: true
runs_on_tv: true
runs_on_vision: true
```

`profile.mobileconfig`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict/>
    </array>
    <key>PayloadDisplayName</key>
    <string>MyFancyProfile</string>
    <key>PayloadIdentifier</key>
    <string>com.kandji.profile.custom.54bef6b3-b25e-44b4-89fd-d528d73939e4</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>54bef6b3-b25e-44b4-89fd-d528d73939e4</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
```

### Custom Script

Each script requires:
1. A directory within a kst repository `scripts` directory containing the script's files
2. Exactly one `info.[plist|yaml|json]` file containing the scripts's associated metadata
3. Exactly one audit script file (filename must start with `audit`)
4. Optionally one remediation script file (filename must start with `remediation`)

```
$ lsd --tree scripts/MyFancyScript
 MyFancyScript
├──  audit.zsh
├──  info.plist
└──  remediation.zsh
```

`info.json`

```json
{
  "id": "b27aa82f-4a6d-4a3b-8097-68ca39eb705b",
  "name": "MyFancyScript",
  "active": false,
  "execution_frequency": "once",
  "restart": false
}
```

`audit.zsh`

```shell
#!/bin/zsh -f
# https://support.kandji.io/kb/custom-scripts-overview

echo "Hello, World!"
exit 0
```

`remediation.zsh`
```shell
#!/bin/zsh -f
# https://support.kandji.io/kb/custom-scripts-overview

echo "Hello, World!"
exit 0
```

## Manually Creating Resources

If you are unable to use the `new` command for any reason, resources can also be created manually

1. Create a new directory (named however you like) to hold your resource in the correct repository subdirectory
   (`profiles` or `scripts`)
2. Create an info file in the directory named `info` with one of the following extensions (`.yaml`, `.json`, `.plist`)
3. Populate the info file with at least an `id` and `name` key/value pair
4. Optionally include additional metadata in the info file
5. Optionally include content in the directory
   - For profiles, a single profile with a `.mobileconfig` extension
   - For scripts, an audit script (and optional remediation script) with filenames starting with `audit` and
     `remediation`, respectively
