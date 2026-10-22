### Connector 1
  1. End1_Wall_Thickness                      (unitless)     [0.8; 6]
  2. End1_Style                               (choice)       hose = Hose connector | mag = Magnetic Flange | flange = Flange | osvacm = osVAC Male | osvacf = osVAC Female
  3. End1_Specialised_Style                   (choice)       disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connetor | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
  4. End1_Measurement                         (choice)       inner = inner | outer = outer
  5. End1_Diameter_mm                         (mm)           [10; 200]
  6. End1_Length_mm                           (mm)           [5; 150]
  7. End1_Rotation                            (integer)      [0; 360]
  8. End1_Taper                               (unitless)     [-5; 5]

### Connector 1 - Extension
  9. End1_Extension_Length                    (integer)      [0; 200]
 10. End1_Extension_Exit_Diameter             (unitless)     [0; 200]
 11. End1_Extension_GridSize                  (unitless)     [0; 1]
 12. End1_Extension_GridWallThickness         (unitless)     [0; 1]
 13. End1_Extension_Text_Size                 (integer)      [0; 10]
 14. End1_Extension_SlipRing                  (choice)       disabled = disabled | notaper = non tapered | inner = inner | outer = outer
 15. End1_Extension_SlipRing_Width            (integer)      [2; 10]
 16. End1_Extension_SlipRing_Support          (choice)       disabled = disabled | enabled = enabled | internal = internal | external = external
 17. End1_Extension_SlipRing_Support_Size     (unitless)     [0.1; 0.4]
 18. End1_Extension_SlipRing_Support_Spacing  (unitless)     [2.5; 10]
 19. End1_Extension_StopThickness             (integer)      [0; 20]
 20. End1_Extension_StopLength                (integer)      [0; 40]
 21. End1_Extension_Stop_Symmetrical          (on/off)       true | false

### Connector 1 - Hose connector
 22. End1_Barbs_Count                         (integer)      [0; 10] (only when End1_Style = hose)
 23. End1_Barbs_Thickness                     (unitless)     [0; 5] (only when End1_Style = hose)
 24. End1_Barbs_Symmetrical                   (on/off)       true | false (only when End1_Style = hose)
 25. End1_Hose_EndCap_Diameter                (unitless)     [0; 200] (only when End1_Style = hose)
 26. End1_Hose_EndCap_Thickness               (unitless)     [0; 1] (only when End1_Style = hose)
 27. End1_Hose_EndCap_GridSize                (unitless)     [0; 1] (only when End1_Style = hose)
 28. End1_Hose_EndCap_GridWallThickness       (unitless)     [0; 1] (only when End1_Style = hose)
 29. End1_Hose_Enable_Threads                 (choice)       disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End1_Style = hose)
 30. End1_Hose_Threads_Pitch                  (integer)      [0; 10] (only when End1_Style = hose)
 31. End1_Hose_Threads_Tooth_Angle            (integer)      [15; 60] (only when End1_Style = hose)
 32. End1_Hose_Threads_Tooth_Height           (integer)      [0; 10] (only when End1_Style = hose)

### Connector 1 - Flange
 33. End1_Flange_Width                        (integer)      [10; 40] (only when End1_Style = flange)
 34. End1_Flange_Thickness                    (integer)      [2; 10] (only when End1_Style = flange)
 35. End1_Flange_Screw_Position               (integer)      [0; 10] (only when End1_Style = flange)
 36. End1_Flange_Screw_Border                 (mm)           [2.5; 10] (only when End1_Style = flange)
 37. End1_Flange_Screw_Count                  (integer)      [2; 8] (only when End1_Style = flange)
 38. End1_Flange_Screw_Diameter               (mm)           [2.5; 10] (only when End1_Style = flange)

### Connector 1 - Magnetic Connector
 39. End1_Magnets_Count                       (integer)      [4; 16] (only when End1_Style = mag)
 40. End1_Magnet_Diameter                     (mm)           [5.2; 21] (only when End1_Style = mag)
 41. End1_Magnet_Thickness                    (mm)           [1.2; 5] (only when End1_Style = mag)
 42. End1_Magnet_Border                       (mm)           [1; 4] (only when End1_Style = mag)
 43. End1_Magnet_ZOffset                      (mm)           [0; 1] (only when End1_Style = mag)
 44. End1_Magnet_Flange_Thickness             (mm)           [3; 12] (only when End1_Style = mag)
 45. End1_Magnet_Flange_Roundover             (on/off)       true | false (only when End1_Style = mag)
 46. End1_Ring                                (choice)       no = No alignment ring | protruding = protruding ring | recessed = Recessed ring (only when End1_Style = mag)
 47. End1_Magnet_Twist_Lock_Size              (choice)       0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End1_Style = mag)

### Transition
 48. Transition_Style                         (choice)       flat = flat | bend+taper = Bend and taper | organicbend = Tapered bend | hull = Hull for multiple end count | none = no transition
 49. Transition_Length                        (integer)      [0; 300]
 50. Transition_Angle                         (integer)      [0; 180]
 51. Transition_Bend_Radius                   (mm, integer)  [0; 300]
 52. Transition_Bend_Pipe_Diameter            (choice)       larger = larger | smaller = smaller | custom = custom
 53. Transition_Custom_Bend_Pipe_Diameter     (unitless)     [10; 200]
 54. Transition_Offset_x                      (unitless)     [-150; 150]
 55. Transition_Offset_y                      (unitless)     [-150; 150]

### Transition Multiple connector settings
 56. Transition_End2_Count                    (integer)      [1; 6]
 57. Transition_HullLength                    (unitless)     [0; 1]
 58. Transition_HullCenter                    (choice)       disabled = disabled | end1 = end1 | end2 = end2 | end3 = end3
 59. Transition_HullCenterLength              (integer)      [0; 10]
 60. Transition_HullyOffset                   (unitless)     [0; 1]
 61. Transition_HullCenterHeight              (integer)      [0; 10]
 62. Transition_End2_Angle                    (integer)      [0; 10]

### Transition Support For Angled Pipes
 63. Transition_Base_Type                     (choice)       none = none | oval = oval | rectangle = rectangle
 64. Transition_Base_Thickness                (integer)      [0; 10]
 65. Transition_Base_Width                    (integer)      [0; 10]
 66. Transition_Base_Length                   (integer)      [0; 10]
 67. Transition_Base_Angle                    (integer)      [0; 10]

### Connector 2
 68. End2_Wall_Thickness                      (unitless)     [0.8; 6]
 69. End2_Style                               (choice)       hose = Hose connector | mag = Magnetic Flange | flange = Flange | nozzle = Nozzle attachment | osvacm = osVAC Male | osvacf = osVAC Female | none = None
 70. End2_Specialised_Style                   (choice)       disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connector | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
 71. End2_Measurement                         (choice)       inner = inner | outer = outer
 72. End2_Diameter_mm                         (mm)           [10; 200]
 73. End2_Length_mm                           (mm)           [5; 150]
 74. End2_Rotation                            (integer)      [0; 360]
 75. End2_Taper                               (unitless)     [-5; 5]

### Connector 2 - Extension
 76. End2_Extension_Length                    (integer)      [0; 200]
 77. End2_Extension_Exit_Diameter             (unitless)     [0; 200]
 78. End2_Extension_GridSize                  (unitless)     [0; 1]
 79. End2_Extension_GridWallThickness         (unitless)     [0; 1]
 80. End2_Extension_Text_Size                 (integer)      [0; 10]
 81. End2_Extension_SlipRing                  (choice)       disabled = disabled | notaper = non tapered | inner = inner | outer = outer
 82. End2_Extension_SlipRing_Width            (integer)      [2; 10]
 83. End2_Extension_SlipRing_Support          (choice)       disabled = disabled | enabled = enabled | internal = internal | external = external
 84. End2_Extension_SlipRing_Support_Size     (unitless)     [0.1; 0.4]
 85. End2_Extension_SlipRing_Support_Spacing  (unitless)     [2.5; 10]
 86. End2_Extension_StopThickness             (integer)      [0; 20]
 87. End2_Extension_StopLength                (integer)      [0; 40]
 88. End2_Extension_Stop_Symmetrical          (on/off)       true | false

### Connector 2 - Hose connector
 89. End2_Barbs_Count                         (integer)      [0; 10] (only when End2_Style = hose)
 90. End2_Barbs_Thickness                     (unitless)     [0; 5] (only when End2_Style = hose)
 91. End2_Barbs_Symmetrical                   (on/off)       true | false (only when End2_Style = hose)
 92. End2_Hose_EndCap_Thickness               (unitless)     [0; 1] (only when End2_Style = hose)
 93. End2_Hose_EndCap_Diameter                (unitless)     [0; 200] (only when End2_Style = hose)
 94. End2_Hose_EndCap_GridSize                (unitless)     [0; 1] (only when End2_Style = hose)
 95. End2_Hose_EndCap_GridWallThickness       (unitless)     [0; 1] (only when End2_Style = hose)
 96. End2_Hose_Enable_Threads                 (choice)       disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End2_Style = hose)
 97. End2_Hose_Threads_Pitch                  (integer)      [0; 10] (only when End2_Style = hose)
 98. End2_Hose_Threads_Tooth_Angle            (integer)      [15; 60] (only when End2_Style = hose)
 99. End2_Hose_Threads_Tooth_Height           (integer)      [0; 10] (only when End2_Style = hose)

### Connector 2 - Flange
100. End2_Flange_Width                        (integer)      [10; 40] (only when End2_Style = flange)
101. End2_Flange_Thickness                    (integer)      [2; 10] (only when End2_Style = flange)
102. End2_Flange_Screw_Position               (integer)      [0; 10] (only when End2_Style = flange)
103. End2_Flange_Screw_Border                 (mm)           [2.5; 10] (only when End2_Style = flange)
104. End2_Flange_Screw_Count                  (integer)      [2; 8] (only when End2_Style = flange)
105. End2_Flange_Screw_Diameter               (mm)           [2.5; 10] (only when End2_Style = flange)

### Connector 2 - Magnetic Flange
106. End2_Magnets_Count                       (integer)      [3; 12] (only when End2_Style = mag)
107. End2_Magnet_Diameter                     (unitless)     [6; 24] (only when End2_Style = mag)
108. End2_Magnet_Thickness                    (unitless)     [1.5; 6] (only when End2_Style = mag)
109. End2_Magnet_Border                       (unitless)     [1; 4] (only when End2_Style = mag)
110. End2_Magnet_ZOffset                      (mm)           [0; 1] (only when End2_Style = mag)
111. End2_Magnet_Flange_Thickness             (unitless)     [5; 20] (only when End2_Style = mag)
112. End2_Magnet_Flange_Roundover             (on/off)       true | false (only when End2_Style = mag)
113. End2_Ring                                (choice)       no = No alignment ring | protruding = Protruding ring | recessed = Recessed ring (only when End2_Style = mag)
114. End2_Magnet_Twist_Lock_Size              (choice)       0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End2_Style = mag)

### Connector 2 - Nozzle
115. End2_Nozzle_Shape                        (choice)       square = square | circle = circle (only when End2_Style = nozzle)
116. End2_Nozzle_Size_x                       (unitless)     [5; 20] (only when End2_Style = nozzle)
117. End2_Nozzle_Size_y                       (unitless)     [2.5; 10] (only when End2_Style = nozzle)
118. End2_Nozzle_Size_z                       (unitless)     [5; 20] (only when End2_Style = nozzle)
119. End2_Nozzle_Tip_Wall_Thickness           (unitless)     [0; 1] (only when End2_Style = nozzle)
120. End2_Nozzle_Radius                       (unitless)     [0; 1] (only when End2_Style = nozzle)
121. End2_Nozzle_Offset_x                     (unitless)     [0; 1] (only when End2_Style = nozzle)
122. End2_Nozzle_Offset_y                     (unitless)     [0; 1] (only when End2_Style = nozzle)
123. End2_Nozzle_Chamfer_Percentage           (unitless)     [0; 1] (only when End2_Style = nozzle)
124. End2_Nozzle_Chamfer_Angle                (unitless)     [0; 1] (only when End2_Style = nozzle)

### Connector 3
125. End3_Wall_Thickness                      (unitless)     [0.8; 6]
126. End3_Style                               (choice)       hose = Hose connector | mag = Magnetic Flange | flange = Flange | nozzle = Nozzle attachement | osvacm = osVAC Male | osvacf = osVAC Female | none = None
127. End3_Specialised_Style                   (choice)       disabled = Disabled | dyson = Dyson connector | camlock = CAMLOCK connector | dw735 = Dewalt DW735x | centec_female = Cen-Tec quick female connect | centec_male = Cen-Tec quick male connect | osvacm32 = osVAC M32 | osvacf32 = osVAC F32 | makita_male = Makita Quick connect Male connector | bosch_sander = Bosch orbital sander | festoolcleanteclug = Festool Cleantec Lug | kobalt = Kobalt Saw Dust Outlet | rigid_nxt = Rigid NXT Vac Hose
128. End3_Measurement                         (choice)       inner = inner | outer = outer
129. End3_Diameter_mm                         (mm)           [10; 200]
130. End3_Length_mm                           (mm)           [5; 150]
131. End3_Rotation                            (integer)      [0; 360]
132. End3_Taper                               (unitless)     [-5; 5]

### Connector 3 - Extension
133. End3_Extension_Length                    (integer)      [0; 200]
134. End3_Extension_Exit_Diameter             (unitless)     [0; 200]
135. End3_Extension_GridSize                  (unitless)     [0; 1]
136. End3_Extension_GridWallThickness         (unitless)     [0; 1]
137. End3_Extension_Text_Size                 (integer)      [0; 10]
138. End3_Extension_SlipRing                  (choice)       disabled = disabled | notaper = non tapered | inner = inner | outer = outer
139. End3_Extension_SlipRing_Width            (integer)      [2; 10]
140. End3_Extension_SlipRing_Support          (choice)       disabled = disabled | enabled = enabled | internal = internal | external = external
141. End3_Extension_SlipRing_Support_Size     (unitless)     [0.1; 0.4]
142. End3_Extension_SlipRing_Support_Spacing  (unitless)     [2.5; 10]
143. End3_Extension_StopThickness             (integer)      [0; 20]
144. End3_Extension_StopLength                (integer)      [0; 40]
145. End3_Extension_Stop_Symmetrical          (on/off)       true | false

### Connector 3 - Hose connector
146. End3_Barbs_Count                         (integer)      [0; 10] (only when End3_Style = hose)
147. End3_Barbs_Thickness                     (unitless)     [0; 5] (only when End3_Style = hose)
148. End3_Barbs_Symmetrical                   (on/off)       true | false (only when End3_Style = hose)
149. End3_Hose_EndCap_Thickness               (unitless)     [0; 1] (only when End3_Style = hose)
150. End3_Hose_EndCap_Diameter                (unitless)     [0; 200] (only when End3_Style = hose)
151. End3_Hose_EndCap_GridSize                (unitless)     [0; 1] (only when End3_Style = hose)
152. End3_Hose_EndCap_GridWallThickness       (unitless)     [0; 1] (only when End3_Style = hose)
153. End3_Hose_Enable_Threads                 (choice)       disabled = disabled | enabled = enabled (left-hand) | reversed = standard (right-hand) (only when End3_Style = hose)
154. End3_Hose_Threads_Pitch                  (integer)      [0; 10] (only when End3_Style = hose)
155. End3_Hose_Threads_Tooth_Angle            (integer)      [15; 60] (only when End3_Style = hose)
156. End3_Hose_Threads_Tooth_Height           (integer)      [0; 10] (only when End3_Style = hose)

### Connector 3 - Flange
157. End3_Flange_Width                        (integer)      [10; 40] (only when End3_Style = flange)
158. End3_Flange_Thickness                    (integer)      [2; 10] (only when End3_Style = flange)
159. End3_Flange_Screw_Position               (integer)      [0; 10] (only when End3_Style = flange)
160. End3_Flange_Screw_Border                 (mm)           [2.5; 10] (only when End3_Style = flange)
161. End3_Flange_Screw_Count                  (integer)      [2; 8] (only when End3_Style = flange)
162. End3_Flange_Screw_Diameter               (mm)           [2.5; 10] (only when End3_Style = flange)

### Connector 3 - Magnetic connector
163. End3_Magnets_Count                       (integer)      [3; 12] (only when End3_Style = mag)
164. End3_Magnet_Diameter                     (unitless)     [6; 24] (only when End3_Style = mag)
165. End3_Magnet_Thickness                    (unitless)     [1.5; 6] (only when End3_Style = mag)
166. End3_Magnet_Border                       (unitless)     [1; 4] (only when End3_Style = mag)
167. End3_Magnet_ZOffset                      (mm)           [0; 1] (only when End3_Style = mag)
168. End3_Magnet_Flange_Thickness             (unitless)     [5; 20] (only when End3_Style = mag)
169. End3_Magnet_Flange_Roundover             (on/off)       true | false (only when End3_Style = mag)
170. End3_Ring                                (choice)       no = No alignment ring | protruding = Protruding ring | recessed = Recessed ring (only when End3_Style = mag)
171. End3_Magnet_Twist_Lock_Size              (choice)       0 = none | 3 = M3 | 3cnc = M3 with CNC Kitchen insert | 4 = M4 | 4cnc = M4 with CNC Kitchen insert | 5 = M5 | 5cnc = M5 with CNC Kitchen insert (only when End3_Style = mag)

### Connector 3 - Nozzle
172. End3_Nozzle_Shape                        (choice)       square = square | circle = circle (only when End3_Style = nozzle)
173. End3_Nozzle_Size_x                       (unitless)     [5; 20] (only when End3_Style = nozzle)
174. End3_Nozzle_Size_y                       (unitless)     [2.5; 10] (only when End3_Style = nozzle)
175. End3_Nozzle_Size_z                       (unitless)     [5; 20] (only when End3_Style = nozzle)
176. End3_Nozzle_Tip_Wall_Thickness           (unitless)     [0; 1] (only when End3_Style = nozzle)
177. End3_Nozzle_Radius                       (unitless)     [0; 1] (only when End3_Style = nozzle)
178. End3_Nozzle_Offset_x                     (unitless)     [0; 1] (only when End3_Style = nozzle)
179. End3_Nozzle_Offset_y                     (unitless)     [0; 1] (only when End3_Style = nozzle)
180. End3_Nozzle_Chamfer_Percentage           (unitless)     [0; 1] (only when End3_Style = nozzle)
181. End3_Nozzle_Chamfer_Angle                (unitless)     [0; 1] (only when End3_Style = nozzle)

### Alignment Ring
182. Draw_Alignment_Ring                      (choice)       end1 = Draw end 1 | end2 = Draw end 2 | no = Don't draw
183. Alignment_Depth                          (mm)           [1; 4]
184. Alignment_Upper_Width                    (mm)           [1.5; 6]
185. Alignment_Lower_Width                    (mm)           [0.2; 1]
186. Alignment_Side_Clearance                 (mm)           [0.12; 0.5]
187. Alignment_Depth_Clearance                (mm)           [0.37; 1.5]
