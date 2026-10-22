### Connector 1
  1. End1_Wall_Thickness                      (unitless)     — Wall thickness [0.8; 6]
  2. End1_Style                               (choice)       — The style of the end: hose = Hose connector | mag = Magnetic Flange | flange = Flange | osvacm = osVAC Male | osvacf = osVAC Female
  3. End1_Specialised_Style                   (choice)       — End1 Specialised Style: disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connetor | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
  4. End1_Measurement                         (choice)       — Is the measurement the adapter's outside or inside diameter?: inner = inner | outer = outer
  5. End1_Diameter_mm                         (mm)           — End 1 diameter of the adapter [10; 200]
  6. End1_Length_mm                           (mm)           — Length of the start connector, including the flange [5; 150]
  7. End1_Rotation                            (integer)      — Rotation around the z axis. Useful for non symmetrical connectors [0; 360]
  8. End1_Taper                               (unitless)     — Taper of the start connector, use negative to taper other direction [-5; 5]

### Connector 1 - Extension
  9. End1_Extension_Length                    (integer)      — Length of the extension [0; 200]
 10. End1_Extension_Exit_Diameter             (unitless)     — Inside diameter at the extension exit. 0 keeps the connector diameter. The change is tapered at 45 degrees [0; 200]
 11. End1_Extension_GridSize                  (unitless)     — Size of the grid in the extension. 0: diameter/6 [0; 1]
 12. End1_Extension_GridWallThickness         (unitless)     — Size of the grid walls in the extension. 0: no grid, -1: uses wall thickness [0; 1]
 13. End1_Extension_Text_Size                 (integer)      — End1 Extension Text Size [0; 10]
 14. End1_Extension_SlipRing                  (choice)       — End1 Extension SlipRing: disabled = disabled | notaper = non tapered | inner = inner | outer = outer
 15. End1_Extension_SlipRing_Width            (integer)      — End1 Extension SlipRing Width [2; 10]
 16. End1_Extension_SlipRing_Support          (choice)       — Add breakaway supports to the slip ring gap: disabled = disabled | enabled = enabled | internal = internal | external = external
 17. End1_Extension_SlipRing_Support_Size     (unitless)     — Diameter of the breakaway supports [0.1; 0.4]
 18. End1_Extension_SlipRing_Support_Spacing  (unitless)     — Approximate spacing between supports around the selected opening [2.5; 10]
 19. End1_Extension_StopThickness             (integer)      — Thickness of hose stop [0; 20]
 20. End1_Extension_StopLength                (integer)      — Length of hose stop [0; 40]
 21. End1_Extension_Stop_Symmetrical          (on/off)       — Should the stop be tapered both sides. Might easier to print: true | false

### Connector 1 - Hose connector
 22. End1_Barbs_Count                         (integer)      — Number of barbs [0; 10] (only when End1_Style = hose)
 23. End1_Barbs_Thickness                     (unitless)     — Thickness of the barbs, default is half wall thickness [0; 5] (only when End1_Style = hose)
 24. End1_Barbs_Symmetrical                   (on/off)       — Should the barbs be tapered both sides. Might be easier to print: true | false (only when End1_Style = hose)
 25. End1_Hose_EndCap_Diameter                (unitless)     — End Cap Inner Diameter [0; 200] (only when End1_Style = hose)
 26. End1_Hose_EndCap_Thickness               (unitless)     — Thickness of end cap [0; 1] (only when End1_Style = hose)
 27. End1_Hose_EndCap_GridSize                (unitless)     — End cap grid size for holes [0; 1] (only when End1_Style = hose)
 28. End1_Hose_EndCap_GridWallThickness       (unitless)     — Thickness of the walls in the end cap [0; 1] (only when End1_Style = hose)
 29. End1_Hose_Enable_Threads                 (choice)       — Enable threads Thread side matches Measurement side. Beta feature does not work with taper: disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End1_Style = hose)
 30. End1_Hose_Threads_Pitch                  (integer)      — Thread Pitch [0; 10] (only when End1_Style = hose)
 31. End1_Hose_Threads_Tooth_Angle            (integer)      — Thread Tooth Angle [15; 60] (only when End1_Style = hose)
 32. End1_Hose_Threads_Tooth_Height           (integer)      — Thread Tooth Height [0; 10] (only when End1_Style = hose)

### Connector 1 - Flange
 33. End1_Flange_Width                        (integer)      — Width of Flange added to the connector diameter [10; 40] (only when End1_Style = flange)
 34. End1_Flange_Thickness                    (integer)      — Thickness of the flange [2; 10] (only when End1_Style = flange)
 35. End1_Flange_Screw_Position               (integer)      — Position of the screws added to the connector diameter, 0 = middle of flange [0; 10] (only when End1_Style = flange)
 36. End1_Flange_Screw_Border                 (mm)           — Minium amount of the material around the magnet holes(mm), 0 = End1_Flange_Width / 4 [2.5; 10] (only when End1_Style = flange)
 37. End1_Flange_Screw_Count                  (integer)      — Number of Screw holes flange [2; 8] (only when End1_Style = flange)
 38. End1_Flange_Screw_Diameter               (mm)           — The diameter of the screws (mm) [2.5; 10] (only when End1_Style = flange)

### Connector 1 - Magnetic Connector
 39. End1_Magnets_Count                       (integer)      — Number of magnets in the connector [4; 16] (only when End1_Style = mag)
 40. End1_Magnet_Diameter                     (mm)           — The diameter of the magnets (mm) [5.2; 21] (only when End1_Style = mag)
 41. End1_Magnet_Thickness                    (mm)           — The thickness of the magnets (mm) [1.2; 5] (only when End1_Style = mag)
 42. End1_Magnet_Border                       (mm)           — Minium amount of the material around the magnets (mm) [1; 4] (only when End1_Style = mag)
 43. End1_Magnet_ZOffset                      (mm)           — Raises the magnet so it is fully enclosed (mm) [0; 1] (only when End1_Style = mag)
 44. End1_Magnet_Flange_Thickness             (mm)           — Thickness of the magnet flange (mm) [3; 12] (only when End1_Style = mag)
 45. End1_Magnet_Flange_Roundover             (on/off)       — Round over the outside edge of the magnetic flange: true | false (only when End1_Style = mag)
 46. End1_Ring                                (choice)       — Include a flange alignment ring: no = No alignment ring | protruding = protruding ring | recessed = Recessed ring (only when End1_Style = mag)
 47. End1_Magnet_Twist_Lock_Size              (choice)       — Magnetic ring Twist lock bolt size (draft setting): 0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End1_Style = mag)

### Transition
 48. Transition_Style                         (choice)       — tapered for hose connections, flat for attaching to a device: flat = flat | bend+taper = Bend and taper | organicbend = Tapered bend | hull = Hull for multiple end count | none = no transition
 49. Transition_Length                        (integer)      — Length of the transition between the two ends [0; 300]
 50. Transition_Angle                         (integer)      — Angle of bend through the transition section [0; 180]
 51. Transition_Bend_Radius                   (mm, integer)  — Radius of transition bend (mm) [0; 300]
 52. Transition_Bend_Pipe_Diameter            (choice)       — Select the bend pipe's inside diameter from the two ends, or enter a custom value: larger = larger | smaller = smaller | custom = custom
 53. Transition_Custom_Bend_Pipe_Diameter     (unitless)     — Inside diameter of the bend pipe when custom is selected [10; 200]
 54. Transition_Offset_x                      (unitless)     — offset for the connector, not supported on taperedbend (x) [-150; 150]
 55. Transition_Offset_y                      (unitless)     — offset for the connector, not supported on taperedbend (y) [-150; 150]

### Transition Multiple connector settings
 56. Transition_End2_Count                    (integer)      — Duplicate the second connector. Adjust angle and bend radius to make it work [1; 6]
 57. Transition_HullLength                    (unitless)     — MulitConnector, connector in hull length [0; 1]
 58. Transition_HullCenter                    (choice)       — MulitConnector, add centre connector: disabled = disabled | end1 = end1 | end2 = end2 | end3 = end3
 59. Transition_HullCenterLength              (integer)      — Transition HullCenterLength [0; 10]
 60. Transition_HullyOffset                   (unitless)     — MulitConnector, connector in hull offset [0; 1]
 61. Transition_HullCenterHeight              (integer)      — MulitConnector, center connector height. default is 2*lengthInHull [0; 10]
 62. Transition_End2_Angle                    (integer)      — Transition End2 Angle [0; 10]

### Transition Support For Angled Pipes
 63. Transition_Base_Type                     (choice)       — Include a flat section on the transition to assist with printing: none = none | oval = oval | rectangle = rectangle
 64. Transition_Base_Thickness                (integer)      — Support Base Additional Thickness; [0; 10]
 65. Transition_Base_Width                    (integer)      — Support Base Width, Default is half diameter [0; 10]
 66. Transition_Base_Length                   (integer)      — Support Base Length Default is 2/3 diameter [0; 10]
 67. Transition_Base_Angle                    (integer)      — Support Base Angle position, default half of Bend Radius; [0; 10]

### Connector 2
 68. End2_Wall_Thickness                      (unitless)     — Wall thickness [0.8; 6]
 69. End2_Style                               (choice)       — End2 Style: hose = Hose connector | mag = Magnetic Flange | flange = Flange | nozzle = Nozzle attachment | osvacm = osVAC Male | osvacf = osVAC Female | none = None
 70. End2_Specialised_Style                   (choice)       — End2 Specialised Style: disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connector | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
 71. End2_Measurement                         (choice)       — Is the measurement the adapter's outside or inside diameter?: inner = inner | outer = outer
 72. End2_Diameter_mm                         (mm)           — End 2 diameter of the adapter [10; 200]
 73. End2_Length_mm                           (mm)           — Length of the start connector, including the flange [5; 150]
 74. End2_Rotation                            (integer)      — Rotation around the z axis. Useful for non symmetrical connectors [0; 360]
 75. End2_Taper                               (unitless)     — Taper of the start connector, use negative to taper other direction [-5; 5]

### Connector 2 - Extension
 76. End2_Extension_Length                    (integer)      — Length of the extension [0; 200]
 77. End2_Extension_Exit_Diameter             (unitless)     — Inside diameter at the extension exit. 0 keeps the connector diameter. The change is tapered at 45 degrees [0; 200]
 78. End2_Extension_GridSize                  (unitless)     — Size of the grid in the extension. 0: diameter/6 [0; 1]
 79. End2_Extension_GridWallThickness         (unitless)     — Size of the grid walls in the extension. 0: no grid, -1: uses wall thickness [0; 1]
 80. End2_Extension_Text_Size                 (integer)      — End2 Extension Text Size [0; 10]
 81. End2_Extension_SlipRing                  (choice)       — End2 Extension SlipRing: disabled = disabled | notaper = non tapered | inner = inner | outer = outer
 82. End2_Extension_SlipRing_Width            (integer)      — End2 Extension SlipRing Width [2; 10]
 83. End2_Extension_SlipRing_Support          (choice)       — Add breakaway supports to the slip ring gap: disabled = disabled | enabled = enabled | internal = internal | external = external
 84. End2_Extension_SlipRing_Support_Size     (unitless)     — Diameter of the breakaway supports [0.1; 0.4]
 85. End2_Extension_SlipRing_Support_Spacing  (unitless)     — Approximate spacing between supports around the selected opening [2.5; 10]
 86. End2_Extension_StopThickness             (integer)      — Thickness of hose stop [0; 20]
 87. End2_Extension_StopLength                (integer)      — Length of hose stop [0; 40]
 88. End2_Extension_Stop_Symmetrical          (on/off)       — Should the stop be tapered both sides. Might easier to print: true | false

### Connector 2 - Hose connector
 89. End2_Barbs_Count                         (integer)      — Number of barbs [0; 10] (only when End2_Style = hose)
 90. End2_Barbs_Thickness                     (unitless)     — Thickness of the barbs, default is half wall thickness [0; 5] (only when End2_Style = hose)
 91. End2_Barbs_Symmetrical                   (on/off)       — Should the barbs be tapered both sides. Might be easier to print: true | false (only when End2_Style = hose)
 92. End2_Hose_EndCap_Thickness               (unitless)     — Thickness of end cap, 0 means disabled [0; 1] (only when End2_Style = hose)
 93. End2_Hose_EndCap_Diameter                (unitless)     — End Cap Inner Diameter [0; 200] (only when End2_Style = hose)
 94. End2_Hose_EndCap_GridSize                (unitless)     — End cap grid size for holes [0; 1] (only when End2_Style = hose)
 95. End2_Hose_EndCap_GridWallThickness       (unitless)     — Thickness of the walls in the end cap [0; 1] (only when End2_Style = hose)
 96. End2_Hose_Enable_Threads                 (choice)       — Enable threads Thread side matches Measurement side. Beta feature does not work with taper: disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End2_Style = hose)
 97. End2_Hose_Threads_Pitch                  (integer)      — Thread Pitch [0; 10] (only when End2_Style = hose)
 98. End2_Hose_Threads_Tooth_Angle            (integer)      — Thread Tooth Angle [15; 60] (only when End2_Style = hose)
 99. End2_Hose_Threads_Tooth_Height           (integer)      — Thread Tooth Height [0; 10] (only when End2_Style = hose)

### Connector 2 - Flange
100. End2_Flange_Width                        (integer)      — Width of Flange added to the connector diameter [10; 40] (only when End2_Style = flange)
101. End2_Flange_Thickness                    (integer)      — Thickness of the flange [2; 10] (only when End2_Style = flange)
102. End2_Flange_Screw_Position               (integer)      — Position of the screws added to the connector diameter, 0 = middle of flange [0; 10] (only when End2_Style = flange)
103. End2_Flange_Screw_Border                 (mm)           — Minium amount of the material around the magnets (mm), 0 = End1_Flange_Width / 4 [2.5; 10] (only when End2_Style = flange)
104. End2_Flange_Screw_Count                  (integer)      — Number of Screw holes flange [2; 8] (only when End2_Style = flange)
105. End2_Flange_Screw_Diameter               (mm)           — The diameter of the screws (mm) [2.5; 10] (only when End2_Style = flange)

### Connector 2 - Magnetic Flange
106. End2_Magnets_Count                       (integer)      — Number of magnets in the flange [3; 12] (only when End2_Style = mag)
107. End2_Magnet_Diameter                     (unitless)     — The diameter of the magnets [6; 24] (only when End2_Style = mag)
108. End2_Magnet_Thickness                    (unitless)     — The thickness of the magnets [1.5; 6] (only when End2_Style = mag)
109. End2_Magnet_Border                       (unitless)     — Size of the material around the magnets [1; 4] (only when End2_Style = mag)
110. End2_Magnet_ZOffset                      (mm)           — Raises the magnet so it is fully enclosed (mm) [0; 1] (only when End2_Style = mag)
111. End2_Magnet_Flange_Thickness             (unitless)     — Inner diameter of the Magnet flange [5; 20] (only when End2_Style = mag)
112. End2_Magnet_Flange_Roundover             (on/off)       — Round over the outside edge of the magnetic flange: true | false (only when End2_Style = mag)
113. End2_Ring                                (choice)       — Include a flange alignment ring: no = No alignment ring | protruding = Protruding ring | recessed = Recessed ring (only when End2_Style = mag)
114. End2_Magnet_Twist_Lock_Size              (choice)       — Magnetic ring twist lock bolt size (draft setting): 0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End2_Style = mag)

### Connector 2 - Nozzle
115. End2_Nozzle_Shape                        (choice)       — Is the measurement the adapter's outside or inside diameter?: square = square | circle = circle (only when End2_Style = nozzle)
116. End2_Nozzle_Size_x                       (unitless)     — End2 Nozzle Size x [5; 20] (only when End2_Style = nozzle)
117. End2_Nozzle_Size_y                       (unitless)     — End2 Nozzle Size y [2.5; 10] (only when End2_Style = nozzle)
118. End2_Nozzle_Size_z                       (unitless)     — End2 Nozzle Size z [5; 20] (only when End2_Style = nozzle)
119. End2_Nozzle_Tip_Wall_Thickness           (unitless)     — End2 Nozzle Tip Wall Thickness [0; 1] (only when End2_Style = nozzle)
120. End2_Nozzle_Radius                       (unitless)     — End2 Nozzle Radius [0; 1] (only when End2_Style = nozzle)
121. End2_Nozzle_Offset_x                     (unitless)     — End2 Nozzle Offset x [0; 1] (only when End2_Style = nozzle)
122. End2_Nozzle_Offset_y                     (unitless)     — End2 Nozzle Offset y [0; 1] (only when End2_Style = nozzle)
123. End2_Nozzle_Chamfer_Percentage           (unitless)     — End2 Nozzle Chamfer Percentage [0; 1] (only when End2_Style = nozzle)
124. End2_Nozzle_Chamfer_Angle                (unitless)     — End2 Nozzle Chamfer Angle [0; 1] (only when End2_Style = nozzle)

### Connector 3
125. End3_Wall_Thickness                      (unitless)     — Wall thickness [0.8; 6]
126. End3_Style                               (choice)       — End3 Style: hose = Hose connector | mag = Magnetic Flange | flange = Flange | nozzle = Nozzle attachement | osvacm = osVAC Male | osvacf = osVAC Female | none = None
127. End3_Specialised_Style                   (choice)       — End3 Specialised Style: disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connector | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
128. End3_Measurement                         (choice)       — Is the measurement the adapter's outside or inside diameter?: inner = inner | outer = outer
129. End3_Diameter_mm                         (mm)           — End 3 diameter of the adapter [10; 200]
130. End3_Length_mm                           (mm)           — Length of the start connector, including the flange [5; 150]
131. End3_Rotation                            (integer)      — Rotation around the z axis. Useful for non symmetrical connectors [0; 360]
132. End3_Taper                               (unitless)     — Taper of the start connector, use negative to taper other direction [-5; 5]

### Connector 3 - Extension
133. End3_Extension_Length                    (integer)      — Length of the extension [0; 200]
134. End3_Extension_Exit_Diameter             (unitless)     — Inside diameter at the extension exit. 0 keeps the connector diameter. The change is tapered at 45 degrees [0; 200]
135. End3_Extension_GridSize                  (unitless)     — Size of the grid in the extension. 0: diameter/6 [0; 1]
136. End3_Extension_GridWallThickness         (unitless)     — Size of the grid walls in the extension. 0: no grid, -1: uses wall thickness [0; 1]
137. End3_Extension_Text_Size                 (integer)      — End3 Extension Text Size [0; 10]
138. End3_Extension_SlipRing                  (choice)       — End3 Extension SlipRing: disabled = disabled | notaper = non tapered | inner = inner | outer = outer
139. End3_Extension_SlipRing_Width            (integer)      — End3 Extension SlipRing Width [2; 10]
140. End3_Extension_SlipRing_Support          (choice)       — Add breakaway supports to the slip ring gap: disabled = disabled | enabled = enabled | internal = internal | external = external
141. End3_Extension_SlipRing_Support_Size     (unitless)     — Diameter of the breakaway supports [0.1; 0.4]
142. End3_Extension_SlipRing_Support_Spacing  (unitless)     — Approximate spacing between supports around the selected opening [2.5; 10]
143. End3_Extension_StopThickness             (integer)      — Thickness of hose stop [0; 20]
144. End3_Extension_StopLength                (integer)      — Length of hose stop [0; 40]
145. End3_Extension_Stop_Symmetrical          (on/off)       — Should the stop be tapered both sides. Might easier to print: true | false

### Connector 3 - Hose connector
146. End3_Barbs_Count                         (integer)      — Number of barbs [0; 10] (only when End3_Style = hose)
147. End3_Barbs_Thickness                     (unitless)     — Thickness of the barbs, default is half wall thickness [0; 5] (only when End3_Style = hose)
148. End3_Barbs_Symmetrical                   (on/off)       — Should the barbs be tapered both sides. Might be easier to print: true | false (only when End3_Style = hose)
149. End3_Hose_EndCap_Thickness               (unitless)     — Thickness of end cap, 0 means disabled [0; 1] (only when End3_Style = hose)
150. End3_Hose_EndCap_Diameter                (unitless)     — End Cap Inner Diameter [0; 200] (only when End3_Style = hose)
151. End3_Hose_EndCap_GridSize                (unitless)     — End cap grid size for holes [0; 1] (only when End3_Style = hose)
152. End3_Hose_EndCap_GridWallThickness       (unitless)     — Thickness of the walls in the end cap [0; 1] (only when End3_Style = hose)
153. End3_Hose_Enable_Threads                 (choice)       — Enable threads Thread side matches Measurement side. Beta feature does not work with taper: disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End3_Style = hose)
154. End3_Hose_Threads_Pitch                  (integer)      — Thread Pitch [0; 10] (only when End3_Style = hose)
155. End3_Hose_Threads_Tooth_Angle            (integer)      — Thread Tooth Angle [15; 60] (only when End3_Style = hose)
156. End3_Hose_Threads_Tooth_Height           (integer)      — Thread Tooth Height [0; 10] (only when End3_Style = hose)

### Connector 3 - Flange
157. End3_Flange_Width                        (integer)      — Width of Flange added to the connector diameter [10; 40] (only when End3_Style = flange)
158. End3_Flange_Thickness                    (integer)      — Thickness of the flange [2; 10] (only when End3_Style = flange)
159. End3_Flange_Screw_Position               (integer)      — Position of the screws added to the connector diameter, 0 = middle of flange [0; 10] (only when End3_Style = flange)
160. End3_Flange_Screw_Border                 (mm)           — Minium amount of the material around the magnets (mm), 0 = End1_Flange_Width / 4 [2.5; 10] (only when End3_Style = flange)
161. End3_Flange_Screw_Count                  (integer)      — Number of Screw holes flange [2; 8] (only when End3_Style = flange)
162. End3_Flange_Screw_Diameter               (mm)           — The diameter of the screws (mm) [2.5; 10] (only when End3_Style = flange)

### Connector 3 - Magnetic connector
163. End3_Magnets_Count                       (integer)      — Number of magnets in the flange [3; 12] (only when End3_Style = mag)
164. End3_Magnet_Diameter                     (unitless)     — The diameter of the magnets [6; 24] (only when End3_Style = mag)
165. End3_Magnet_Thickness                    (unitless)     — The thickness of the magnets [1.5; 6] (only when End3_Style = mag)
166. End3_Magnet_Border                       (unitless)     — Size of the material around the magnets [1; 4] (only when End3_Style = mag)
167. End3_Magnet_ZOffset                      (mm)           — Raises the magnet so it is fully enclosed (mm) [0; 1] (only when End3_Style = mag)
168. End3_Magnet_Flange_Thickness             (unitless)     — Inner diameter of the Magnet flange [5; 20] (only when End3_Style = mag)
169. End3_Magnet_Flange_Roundover             (on/off)       — Round over the outside edge of the magnetic flange: true | false (only when End3_Style = mag)
170. End3_Ring                                (choice)       — Include a flange alignment ring: no = No alignment ring | protruding = Protruding ring | recessed = Recessed ring (only when End3_Style = mag)
171. End3_Magnet_Twist_Lock_Size              (choice)       — Magnetic ring twist lock bolt size (draft setting): 0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End3_Style = mag)

### Connector 3 - Nozzle
172. End3_Nozzle_Shape                        (choice)       — Is the measurement the adapter's outside or inside diameter?: square = square | circle = circle (only when End3_Style = nozzle)
173. End3_Nozzle_Size_x                       (unitless)     — End3 Nozzle Size x [5; 20] (only when End3_Style = nozzle)
174. End3_Nozzle_Size_y                       (unitless)     — End3 Nozzle Size y [2.5; 10] (only when End3_Style = nozzle)
175. End3_Nozzle_Size_z                       (unitless)     — End3 Nozzle Size z [5; 20] (only when End3_Style = nozzle)
176. End3_Nozzle_Tip_Wall_Thickness           (unitless)     — End3 Nozzle Tip Wall Thickness [0; 1] (only when End3_Style = nozzle)
177. End3_Nozzle_Radius                       (unitless)     — End3 Nozzle Radius [0; 1] (only when End3_Style = nozzle)
178. End3_Nozzle_Offset_x                     (unitless)     — End3 Nozzle Offset x [0; 1] (only when End3_Style = nozzle)
179. End3_Nozzle_Offset_y                     (unitless)     — End3 Nozzle Offset y [0; 1] (only when End3_Style = nozzle)
180. End3_Nozzle_Chamfer_Percentage           (unitless)     — End3 Nozzle Chamfer Percentage [0; 1] (only when End3_Style = nozzle)
181. End3_Nozzle_Chamfer_Angle                (unitless)     — End3 Nozzle Chamfer Angle [0; 1] (only when End3_Style = nozzle)

### Alignment Ring
182. Draw_Alignment_Ring                      (choice)       — draw just the alignment ring: end1 = Draw end 1 | end2 = Draw end 2 | no = Don't draw
183. Alignment_Depth                          (mm)           — Alignment depth in to flange (mm) [1; 4]
184. Alignment_Upper_Width                    (mm)           — Alignment upper width at widest part (mm) [1.5; 6]
185. Alignment_Lower_Width                    (mm)           — Alignment lower width at narrowest part (mm) [0.2; 1]
186. Alignment_Side_Clearance                 (mm)           — Alignment side clearance, to give nice fit (mm) [0.12; 0.5]
187. Alignment_Depth_Clearance                (mm)           — Alignment Depth Clearance, to prevent hitting bottom (mm) [0.37; 1.5]
