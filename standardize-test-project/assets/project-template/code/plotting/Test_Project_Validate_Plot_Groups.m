function groups = Test_Project_Validate_Plot_Groups(view, panels)
%TEST_PROJECT_VALIDATE_PLOT_GROUPS Optional, lossless overview arrangement.
groups=struct([]);
if ~isfield(view,'groups')||isempty(view.groups), return; end
groups=view.groups;
if ~isfield(view,'grid_size')||~isnumeric(view.grid_size)||numel(view.grid_size)~=2|| ...
        any(~isfinite(view.grid_size))||any(view.grid_size<1)||any(mod(view.grid_size,1))
    error('TestProject:Plot:GroupLayout','grid_size must contain two positive integers.');
end
if ~isstruct(groups)||~all(isfield(groups,{'id','title','panel_ids','position'}))
    error('TestProject:Plot:GroupLayout','Incomplete group contract.');
end
gridSize=view.grid_size(:)'; covered={}; groupIds={}; occupied=false(gridSize);
for k=1:numel(groups)
    if mod(k-1,12)==0, occupied(:)=false; end
    g=groups(k); p=g.position;
    if ~ischar(g.id)||isempty(g.id)||ismember(g.id,groupIds)||~ischar(g.title)|| ...
            ~iscellstr(g.panel_ids)||isempty(g.panel_ids)||~isnumeric(p)||numel(p)~=4|| ...
            any(~isfinite(p))||any(p<1)||any(mod(p,1))
        error('TestProject:Plot:GroupLayout','Invalid group ID, title, panel IDs, or position.');
    end
    if p(1)+p(3)-1>gridSize(1)||p(2)+p(4)-1>gridSize(2)
        error('TestProject:Plot:GroupLayout','Group position exceeds the grid.');
    end
    r=p(1):p(1)+p(3)-1; c=p(2):p(2)+p(4)-1;
    if any(occupied(r,c),'all'), error('TestProject:Plot:GroupLayout','Group positions overlap.'); end
    occupied(r,c)=true; groupIds{end+1}=g.id; %#ok<AGROW>
    covered=[covered reshape(g.panel_ids,1,[])]; %#ok<AGROW>
end
if numel(unique(covered))~=numel(covered)||numel(covered)~=numel(panels)|| ...
        ~all(ismember(covered,{panels.id}))
    error('TestProject:Plot:GroupLayout','Groups must cover every panel exactly once.');
end
end
