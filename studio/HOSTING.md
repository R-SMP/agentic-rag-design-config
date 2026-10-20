# The online Studio

`python -m studio --online` serves the MAS Studio to everyone who has its
access code, on **one shared setup** (MAS-blueprint P7b-lite).  It runs from
the same Docker image as the configurator, as a service of its own.

## On Railway

1. In the project: **New → GitHub Repo**, this repository.  In the new
   service, **Settings → Source**, branch `MAS-studio-deploy`: it moves only
   when you decide, and each push to it deploys the Studio again.
2. **Settings → Deploy → Custom Start Command**:

       python -m studio --online --host 0.0.0.0

   The port is Railway's `PORT`.  (Without this command the image starts the
   configurator, as the Dockerfile says.)
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
  one; a change shows for the others when they reload.
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
