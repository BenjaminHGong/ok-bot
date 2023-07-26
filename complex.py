import sys
sys.set_int_max_str_digits(0)
_CUTOFF = 1536

def multiply(x, y):
	if x.bit_length() <= _CUTOFF or y.bit_length() <= _CUTOFF:
		return x * y
	
	else:
		n = max(x.bit_length(), y.bit_length())
		half = (n + 32) // 64 * 32
		mask = (1 << half) - 1
		xlow = x & mask
		ylow = y & mask
		xhigh = x >> half
		yhigh = y >> half
		
		a = multiply(xhigh, yhigh)
		b = multiply(xlow + xhigh, ylow + yhigh)
		c = multiply(xlow, ylow)
		d = b - a - c
		return (((a << half) + d) << half) + c

def fibonacci(n):
  if n == 0:
    return (0, 1)
  else:
    a, b = fibonacci(n // 2)
    c = multiply(a, (multiply(b, 2) - a))
    d = multiply(a, a) + multiply(b, b)
    if n % 2 == 0:
      return (c, d)
    else:
      return (d, c + d)
 
def multi_msg(seq):
    seq = str(seq)
    while seq:
        yield int(seq[:2000])
        seq = seq[2000:]
