function varargout = serialport(varargin)
setappdata(0,'TemplateHardwareAttempts',getappdata(0,'TemplateHardwareAttempts')+1);
error('template:HardwareForbidden','No hardware I/O is permitted in this demo.');
end
