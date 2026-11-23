# Control mode is a config option, absolute first

v1 maps the Pointer to the screen through the Active region (absolute control mode), because a cursor that follows the finger is the clearest demo. Relative, trackpad-style movement with a clutch is wanted later, and suits lying in bed better. We decided the control mode is selected by config and sits behind one interface, so relative can be added without rewriting the pipeline. The cost is a small abstraction in v1 that only has one implementation.

Status: accepted
