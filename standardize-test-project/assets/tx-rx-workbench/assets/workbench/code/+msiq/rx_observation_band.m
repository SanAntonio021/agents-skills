function [a,b]=rx_observation_band(action,x,y)
%RX_OBSERVATION_BAND Convert observation-only positive-frequency bounds (Hz).
validateattributes(x,{'numeric'},{'scalar','real','finite','nonnegative'});
validateattributes(y,{'numeric'},{'scalar','real','finite','positive'});
switch char(action)
    case 'from_legacy'
        a=max(0,x-y/2); b=x+y/2;
    case 'to_legacy'
        assert(y>x,'RX_Workbench:ObservationBand','功率统计频段上限必须大于下限。');
        a=(x+y)/2; b=y-x;
    otherwise
        error('RX_Workbench:ObservationBand','未知频段转换。');
end
end
