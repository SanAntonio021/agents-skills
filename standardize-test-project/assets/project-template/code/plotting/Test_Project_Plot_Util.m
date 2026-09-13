function out = Test_Project_Plot_Util(action, varargin)
%TEST_PROJECT_PLOT_UTIL Small shared rendering operations (no analysis or I/O).
switch action
    case 'option'
        s=varargin{1}; key=varargin{2}; out=varargin{3};
        if isfield(s,key) && ~isempty(s.(key)), out=s.(key); end
    case 'decorate'
        ax=varargin{1}; options=varargin{2};
        style=Test_Project_Plot_Style();
        style.FontSize=Test_Project_Plot_Util('option',options,'font_size',10);
        Test_Project_Apply_Axes_Style(ax,style);
        title(ax,Test_Project_Plot_Util('option',options,'title',''), ...
            'Interpreter','none','FontWeight','normal','FontSize',style.FontSize+1);
        out=[];
    case 'line'
        ax=varargin{1}; tag=varargin{2}; x=varargin{3}; y=varargin{4};
        out=findobj(ax,'Type','line','Tag',tag);
        if isempty(out), out=line(ax,x,y,'Tag',tag); else, out=out(1); set(out,'XData',x,'YData',y); end
        delete(findobj(ax,'Tag','test_plot_placeholder'));
    case 'envelope'
        y=varargin{1}(:); budget=max(4,round(varargin{2})); n=numel(y);
        if n<=budget, out=(1:n)'; return; end
        edges=round(linspace(1,n+1,floor(budget/2)+1)); out=zeros(2*(numel(edges)-1),1);
        for k=1:numel(edges)-1
            first=edges(k); last=edges(k+1)-1;
            [~,lo]=min(y(first:last)); [~,hi]=max(y(first:last));
            out(2*k-1:2*k)=sort([first+lo-1; first+hi-1]);
        end
        out=unique([1;out;n]);
    case 'placeholder'
        ax=varargin{1}; reason=varargin{2};
        delete(findobj(ax,'Type','line')); delete(findobj(ax,'Tag','test_plot_note'));
        out=findobj(ax,'Tag','test_plot_placeholder');
        if isempty(out), out=text(ax,.5,.5,'','Units','normalized','HorizontalAlignment','center','Tag','test_plot_placeholder'); end
        set(out,'String',reason,'Interpreter','none','FontSize',10);
    case 'note'
        ax=varargin{1}; txt=varargin{2}; out=findobj(ax,'Tag','test_plot_note');
        if isempty(out), out=text(ax,.98,.98,'','Units','normalized','HorizontalAlignment','right','VerticalAlignment','top','Tag','test_plot_note'); end
        set(out,'String',txt,'Interpreter','none','FontSize',max(7,ax.FontSize-1),'BackgroundColor','w','Margin',1);
    case 'color'
        role=char(varargin{1}); out=[0 114 178]/255;
        if strcmpi(role,'Q'), out=[213 85 0]/255; end
    otherwise
        error('TestProject:Plot:UnknownOperation','Unknown rendering operation.');
end
end
