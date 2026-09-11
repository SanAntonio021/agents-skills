function if_write_summary(out)
%IF_WRITE_SUMMARY Separate role column prevents trial/formal count mixing.
path=fullfile(out.run_dir,'summary.csv'); temporary=[path '.tmp'];
fid=Result_Open_File_Retry(temporary,'w'); cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'attempt,role,pre_scan,post_scan,pre_setting,i_setting,q_setting,valid,pre_errors,pre_bits,pre_BER,MER\n');
fprintf(fid,'count,text,dB,dB,dB,dB,dB,logical,count,count,ratio,dB\n');
for k=1:numel(out.observations)
    o=out.observations{k};
    fprintf(fid,'%d,%s,%.15g,%.15g,%.15g,%.15g,%.15g,%d,%.15g,%.15g,%.15g,%.15g\n', ...
        o.attempt,o.role,o.group,o.point,o.setting.pre_db,o.setting.i_db,o.setting.q_db, ...
        o.metrics.valid,o.metrics.pre_error_count,o.metrics.pre_bit_count,o.metrics.pre_ber,o.metrics.mer_db);
end
clear cleanup;
[ok,message]=movefile(temporary,path,'f'); assert(ok,'msiq:if:SummarySave','%s',message);
end
