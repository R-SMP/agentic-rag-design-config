"""UII_PARAMETER_LIST_ENABLED and DCOI_KNOWS_PARAMS_RANGES — both positions.

Round 5 (extra_utilities/prompt_reduction_round5_changes.md) added two
prompt toggles.  Both work by conditional regions resolved in
``agents/shared/prompts.apply_flag_filters``:

  <<UII_PARAMS_ON>> / <<UII_PARAMS_OFF>>     UII_PARAMETER_LIST_ENABLED
  <<DCOI_RANGES_ON>> / <<DCOI_RANGES_OFF>>   DCOI_KNOWS_PARAMS_RANGES

What this guards, beyond "the flag does something":

 1. The OFF position of the UII toggle must remove the parameter VOCABULARY,
    not just the heading — a half-stripped list is worse than either state.
 2. The ON position must still be the round-5 UII copy, i.e. the RED spans
    ([037]-[041]) stay deleted whichever way the toggle sits.  Turning the
    list back on must not resurrect the middlePos formula or the ~30%-chord
    sentence.
 3. Neither marker may reach an assembled prompt in either position.
 4. Neither toggle may introduce a blank-line run — the residue class round 4
    found had already shipped.

Run:  py -3.13 extra_utilities/smoke_test_prompt_toggles.py
"""
import sys, os, re
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "extra_utilities", "prompt_pdf"))
import bootstrap
bootstrap.install()
import workflow_settings.settings as S
S.SYSTEM_TOPOLOGY = 7
S.RAG_ENABLED = False
from agents.shared import prompts as P

RUN = re.compile(r"\n{3,}")

FAILS = []


def check(label, cond, extra=""):
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", label,
                          ("   " + str(extra)) if not cond else ""))
    if not cond:
        FAILS.append(label)


def uii(flag):
    S.UII_PARAMETER_LIST_ENABLED = flag
    return P._build_template("user_input_inspector")


def dcoi(flag):
    S.DCOI_KNOWS_PARAMS_RANGES = flag
    return P._build_template("dc_output_inspector")


print("--- UII_PARAMETER_LIST_ENABLED ---")
off, on = uii(False), uii(True)
check("OFF: no 'Design Configurator Parameters' heading",
      "Design Configurator Parameters" not in off)
check("ON : heading present", "Design Configurator Parameters" in on)
# The `calculate` worked example legitimately shows `outerCamber:` /
# `innerChord` as line labels — a user may well type those words, and the
# DCIC's "Parameter-level entries" covers exactly that case.  Every OTHER
# parameter name must be gone.
check("OFF: no parameter names outside the calculate worked example",
      not any(n in off for n in ("impellerRadius", "innerMaxPos", "middlePos",
                                 "bladeCount", "impellerThickness",
                                 "outerMaxPos", "middleChord")))
check("ON : all 16 names present",
      all(n in on for n in ("bladeCount", "impellerRadius", "impellerThickness",
                            "innerThickness", "innerMaxPos", "innerCamber",
                            "innerChord", "innerAngle", "middlePos",
                            "middleChord", "middleAngle", "outerThickness",
                            "outerMaxPos", "outerCamber", "outerChord",
                            "outerAngle")))
check("ON : RED span gone — ring-HEIGHT note",
      "outer-ring HEIGHT is not a parameter" not in on)
check("ON : RED span gone — hub parenthetical",
      "FIXED cylinder of radius 8 mm" not in on)
check("ON : RED span gone — MaxPos / thickness notes",
      "CAMBER crest only" not in on and "~30% of chord" not in on)
check("ON : RED span gone — middlePos radius formula",
      "radius = 4 + middlePos" not in on)
check("ON : middlePos keeps its range", "1 = tip [0.3; 0.7]" in on)
check("no marker leaks either way",
      "<<UII_PARAMS" not in off and "<<UII_PARAMS" not in on)
check("OFF is shorter", len(off) < len(on), (len(off), len(on)))
check("neither position adds a blank-line run",
      len(RUN.findall(off)) == len(RUN.findall(on)) == 0)
S.UII_PARAMETER_LIST_ENABLED = False

print("--- DCOI_KNOWS_PARAMS_RANGES ---")
doff, don = dcoi(False), dcoi(True)
check("OFF: 'NAMES, not the allowed ranges'",
      "You are given the NAMES, not the allowed ranges." in doff)
check("ON : 'NAMES and the allowed ranges'",
      "You are given the NAMES and the allowed ranges." in don)
check("OFF: no ranges in the list", "[60; 80]" not in doff)
check("ON : all 16 ranges present",
      all(r in don for r in ("[3; 6]", "[60; 80]", "[1; 5]", "[3; 24]",
                             "[2; 8]", "[0; 9]", "[3; 11]", "[2; 25]",
                             "[0.3; 0.7]", "[10; 30]")))
check("no marker leaks either way",
      "<<DCOI_RANGES" not in doff and "<<DCOI_RANGES" not in don)
# ONE run sits before "### Tool-use hard rules" in the pre-round-5 prompt too;
# assert the toggle adds none of its own rather than that there are zero.
check("the toggle adds no blank-line run of its own",
      len(RUN.findall(don)) == len(RUN.findall(doff)) == 1)
S.DCOI_KNOWS_PARAMS_RANGES = False

print()
if FAILS:
    print("FAIL - %d: %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("PASS - both toggles behave in both positions.")
