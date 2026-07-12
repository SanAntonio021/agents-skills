Attribute VB_Name = "SlideArchive"
Option Explicit

Private Const TAG_MARKER As String = "PFR_ARCHIVE_MARKER"
Private Const TAG_SOURCE_SLIDE_ID As String = "PFR_ARCHIVE_SOURCE_SLIDE_ID"
Private Const TAG_SOURCE_SLIDE_INDEX As String = "PFR_ARCHIVE_SOURCE_SLIDE_INDEX"
Private Const TAG_VERSION As String = "PFR_ARCHIVE_VERSION"
Private Const TAG_TIMESTAMP As String = "PFR_ARCHIVE_TIMESTAMP"
Private Const DIALOG_TITLE As String = "留档当前页"

Public Sub ArchiveCurrentSlide(ByVal control As Office.IRibbonControl)
    Call ArchiveCurrentSlideCore(True)
End Sub

' Integration tests call this function to avoid blocking error dialogs.
Public Function PFR_TestArchiveCurrentSlide() As Boolean
    PFR_TestArchiveCurrentSlide = ArchiveCurrentSlideCore(False)
End Function

Private Function ArchiveCurrentSlideCore(ByVal showErrors As Boolean) As Boolean
    Dim activeDeck As Presentation
    Dim sourceSlide As Slide
    Dim archivedSlide As Slide
    Dim duplicatedSlides As SlideRange
    Dim sourceIndex As Long
    Dim sourceSlideId As Long
    Dim archiveVersion As Long
    Dim failureMessage As String

    On Error GoTo UnexpectedFailure

    If Application.Presentations.Count = 0 Then
        ReportFailure "没有打开的演示文稿。", showErrors
        Exit Function
    End If

    Set activeDeck = Application.ActivePresentation
    If activeDeck Is Nothing Then
        ReportFailure "没有活动演示文稿。", showErrors
        Exit Function
    End If

    If Len(activeDeck.Path) = 0 Then
        ReportFailure "当前演示文稿尚未保存。请先普通保存一次。", showErrors
        Exit Function
    End If

    If activeDeck.ReadOnly = msoTrue Then
        ReportFailure "当前演示文稿为只读，无法留档。", showErrors
        Exit Function
    End If

    Set sourceSlide = GetCurrentSlide()
    If sourceSlide Is Nothing Then
        ReportFailure "没有活动页。请先选中要留档的页面。", showErrors
        Exit Function
    End If

    If IsArchivedCopy(sourceSlide) Then
        ReportFailure "当前页已经是历史副本。", showErrors
        Exit Function
    End If

    sourceIndex = sourceSlide.SlideIndex
    sourceSlideId = sourceSlide.SlideID
    archiveVersion = NextArchiveVersion(activeDeck, sourceSlideId)

    Set duplicatedSlides = sourceSlide.Duplicate
    Set archivedSlide = duplicatedSlides(1)
    archivedSlide.MoveTo activeDeck.Slides.Count
    archivedSlide.SlideShowTransition.Hidden = msoTrue
    archivedSlide.Tags.Add TAG_MARKER, "1"
    archivedSlide.Tags.Add TAG_SOURCE_SLIDE_ID, CStr(sourceSlideId)
    archivedSlide.Tags.Add TAG_SOURCE_SLIDE_INDEX, CStr(sourceIndex)
    archivedSlide.Tags.Add TAG_VERSION, CStr(archiveVersion)
    archivedSlide.Tags.Add TAG_TIMESTAMP, Format$(Now, "yyyy-mm-dd HH:nn:ss")

    activeDeck.Save
    RestoreSourceSelection sourceSlide, sourceIndex

    ArchiveCurrentSlideCore = True
    Exit Function

UnexpectedFailure:
    failureMessage = Err.Description
    On Error Resume Next
    If Not archivedSlide Is Nothing Then archivedSlide.Delete
    If Not sourceSlide Is Nothing Then RestoreSourceSelection sourceSlide, sourceIndex
    On Error GoTo 0
    ReportFailure "留档失败：" & failureMessage, showErrors
End Function

Private Function GetCurrentSlide() As Slide
    On Error Resume Next

    If Application.ActiveWindow Is Nothing Then Exit Function

    If Application.ActiveWindow.Selection.Type = ppSelectionSlides Then
        If Application.ActiveWindow.Selection.SlideRange.Count = 1 Then
            Set GetCurrentSlide = Application.ActiveWindow.Selection.SlideRange(1)
            Exit Function
        End If
    End If

    Set GetCurrentSlide = Application.ActiveWindow.View.Slide
    On Error GoTo 0
End Function

Private Function IsArchivedCopy(ByVal candidate As Slide) As Boolean
    IsArchivedCopy = (candidate.Tags.Item(TAG_MARKER) = "1")
End Function

Private Function NextArchiveVersion(ByVal activeDeck As Presentation, ByVal sourceSlideId As Long) As Long
    Dim candidate As Slide
    Dim candidateVersion As Long
    Dim highestVersion As Long

    For Each candidate In activeDeck.Slides
        If candidate.Tags.Item(TAG_MARKER) = "1" Then
            If candidate.Tags.Item(TAG_SOURCE_SLIDE_ID) = CStr(sourceSlideId) Then
                candidateVersion = CLng(Val(candidate.Tags.Item(TAG_VERSION)))
                If candidateVersion > highestVersion Then highestVersion = candidateVersion
            End If
        End If
    Next candidate

    NextArchiveVersion = highestVersion + 1
End Function

Private Sub RestoreSourceSelection(ByVal sourceSlide As Slide, ByVal sourceIndex As Long)
    On Error Resume Next
    If Application.ActiveWindow Is Nothing Then Exit Sub
    Application.ActiveWindow.View.GotoSlide sourceIndex
    sourceSlide.Select
    On Error GoTo 0
End Sub

Private Sub ReportFailure(ByVal message As String, ByVal showErrors As Boolean)
    If showErrors Then MsgBox message, vbExclamation + vbOKOnly, DIALOG_TITLE
End Sub
