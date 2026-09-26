# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private reporting instead (**Security → Report a vulnerability** on the repository page), with a description and, if possible, a way to reproduce it.

lineova doesn't execute or fetch anything from its inputs. The generated HTML pages contain only inline scripts written by lineova. Text in charts (titles, labels, tooltips) is escaped before it is written to SVG and HTML.
