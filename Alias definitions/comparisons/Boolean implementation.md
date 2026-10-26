In this implementation, False is stored as 0, and True is stored as 1. As such, an if block can be implemented like so:
```barebones
while condition not 0 do;
    <code if the condition is true>
    clear condition;
end;
```
_(note that this destroys the value of the condition, so copying it may be necessary)_

Similarly, an if-else block can be done like so:
```barebones
using comparisons;
not_condition = not condition;
while condition not 0 do;
    <code if the condition is true>
    clear condition;
end;
while not_condition not 0 do;
    <code if the condition is false>
    clear not_condition;
end;
```