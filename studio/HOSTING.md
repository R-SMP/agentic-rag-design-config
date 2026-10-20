# The online Studio

The MAS Studio runs online in one of two ways, on **one shared setup**
(MAS-blueprint P7b-lite):

* **Inside the configurator's own deploy** (the usual way): the app's start
  page (`/`) offers the configurator (`/configurator`) and the MAS Studio
  (`/studio/`, `studio/embedded.py`).  Nothing to set up: the Studio comes
  with every deploy of the app, asks for the app's own `INVITE_CODE`, and
  works on a copy of the app's setup (`workspace/dc_pack`, or the folder in
  `STUDIO_WORKSPACE`), so the running configurator never changes.  It is
  made the first time someone opens it.  **The app's keys are in the same
  server**: a tool's code run by Test tool or Validate could read them
  (TODO F122) -- give the code only to people you trust.
* **On its own**, `python -m studio --online`: a service of its own, with
  no key at all.  The rest of this file is about that way.

## On Railway, on its own

1. In the project: **New → GitHub Repo**, this repository.  In the new
   service, **Settings → Source**, branch `MAS-studio-deploy`: it moves only
   when you decide, and each push to it deploys the Studio again.
2. **Settings → Deploy → Custom Start Command**:

       python -m studio --online --host 0.0.0.0

   The port is Railway's `PORT`.  (Without this command the image starts the
   configurator, with the Studio inside it, as the Dockerfile says.)
3. **Variables**:

   | Variable | Needed | What it is |
   |---|---|---|
   | `INVITE_CODE` | yes | The Studio's access code, its own (not the configurator's).  Without it the Studio does not start. |
   | `CONFIGURATOR_URL` | no | The configurator's address (e.g. the live propeller app), linked from the access-code page and the landing page. |
   | `STUDIO_SECRET` | no | Signs the browsers' access cookies; without it each start makes a new one and everyone types the code again. |

   No LLM, database or storage key: the Studio needs none, and must hold
   none -- anyone with the code can run a tool's code on it.
4. **Settings → Networking → Generate Domain**: the Studio's address.
5. Keep **one** replica: the shared setup is on that one container's disk.

## What to know

* **One shared setup.**  Everyone with the code sees and changes the same
  one; a change shows for the others when they reload.  Inside the
  configurator's deploy too.
* **It is not kept** when the Studio restarts or is deployed again: it goes
  back to the propeller example.  Download setup file keeps the work, Import
  a setup brings it back.  A Railway volume mounted at `/app/workspace`
  would keep it (TODO F120).
* **Test tool and Validate run tool code on the server**: give the code only
  to people you trust.
* **Prepare for GitHub** runs on your own computer, in a downloaded package
  (`python -m studio prepare`).

## Try it on your computer

    INVITE_CODE=some-code python -m studio --online

opens http://127.0.0.1:8770/ ; the shared setup lives in `workspace/`, which
git ignores (`--workspace <folder>` puts it elsewhere).
