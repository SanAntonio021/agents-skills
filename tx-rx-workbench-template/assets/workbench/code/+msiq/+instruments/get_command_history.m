function history = get_command_history()
%GET_COMMAND_HISTORY Return ordered mock/real SCPI command records.

history = msiq.instruments.io_audit('get_command_history', '');
end
