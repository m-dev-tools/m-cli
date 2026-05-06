COMBO ;-- combined fixture: commands + intrinsics + ISVs + comment lines
 ; banner comment must be preserved verbatim
 S X=1,Y=2
 W $L(X),! W $E("hi",1,1),!
 I $T W "passed",!
 Q
