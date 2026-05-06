COMBO ;-- combined fixture: commands + intrinsics + ISVs + comment lines
 ; banner comment must be preserved verbatim
 set X=1,Y=2
 write $length(X),! write $extract("hi",1,1),!
 if $test write "passed",!
 quit
