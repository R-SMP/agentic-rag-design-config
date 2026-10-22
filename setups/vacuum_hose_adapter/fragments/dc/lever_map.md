## Which lever moves what

**Each end** (connector 1 and connector 2; connector 3 only for a ``hull``
transition's centre port):
* ``End<N>_Style`` picks what the end is — a hose connector, a magnetic
  flange, a flat flange, an osVAC fitting (end 2 also a nozzle, or none).
  ``End<N>_Specialised_Style``, when not ``disabled``, replaces it with a
  ready-made fitting for a named system (Dyson, CAMLOCK, Festool …).
* ``End<N>_Diameter_mm`` and ``End<N>_Measurement`` size the fit together:
  with ``outer`` the diameter is the end's OUTSIDE — it slides INTO a hose or
  port of that inner diameter; with ``inner`` it is the end's INSIDE — it
  slides OVER a pipe or port of that outer diameter.
* ``End<N>_Length_mm`` is how far the end reaches into (or over) its
  partner; ``End<N>_Taper`` narrows it along that length for a snug push fit
  (0 = straight; a negative value tapers the other way);
  ``End<N>_Wall_Thickness`` sets its wall.
* The settings of an end's own style — barbs, end cap and threads for a hose
  connector; screws for a flange; magnets for a magnetic flange; the size of
  a nozzle — matter only while that style is chosen; their list entries say
  so ("only when …").
* An end's extension (``End<N>_Extension_*``) adds a straight run beyond the
  connector: its length, an exit diameter, a stop ring that keeps the adapter
  from being pulled into the hose (``StopThickness`` and ``StopLength``), a
  slip ring, a grid.

**The transition** joins the two ends:
* ``Transition_Style`` — ``bend+taper`` (a taper, bent when an angle is set),
  ``organicbend`` (a curved, tapered bend), ``flat`` (a flat plate: the
  transition length becomes its thickness), ``hull`` (several second ends),
  ``none``.
* ``Transition_Length`` sets how long the change from one diameter to the
  other is; ``Transition_Angle`` and ``Transition_Bend_Radius`` bend it;
  ``Transition_Offset_x`` / ``Transition_Offset_y`` shift the second end
  sideways (not with ``organicbend``).
* ``Transition_End2_Count`` repeats the second end (a splitter); with more
  than one, the angle and the bend radius must make room for them.

All lengths and diameters are in mm.
