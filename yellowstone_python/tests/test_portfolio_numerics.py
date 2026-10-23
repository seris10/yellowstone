"""Invalid prescribed river forcing checks."""
import pytest
from yellowstone_python.river.river_transport import Series


@pytest.mark.parametrize('forcing',[
    {'times_s':[0,0],'values':[1,2]},
    {'times_s':[0,10],'values':[1,float('nan')]},
    {'times_s':[0],'values':[True]},
    {'times_s':[1],'values':[15]},
])
def test_invalid_forcing_is_rejected(forcing):
    with pytest.raises(ValueError):Series.parse(forcing)
